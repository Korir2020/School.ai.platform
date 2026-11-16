"""Private asset storage and malware-scanner integration.

Local filesystem storage is deliberately development-only. Production must
configure a durable private backend; an unconfigured or failed scanner never
clears an asset for delivery.
"""

import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.module_loading import import_string


class PrivateAssetStorageUnavailable(Exception):
    """Raised when a safe private storage backend is not configured."""


def get_private_asset_storage():
    backend = (getattr(settings, "LEARNING_PRIVATE_ASSET_STORAGE_BACKEND", "") or "").strip()
    if backend:
        try:
            storage = import_string(backend)()
        except Exception as exc:
            raise PrivateAssetStorageUnavailable("Private storage backend is unavailable.") from exc
        if not all(callable(getattr(storage, method, None)) for method in ("save", "open", "delete")):
            raise PrivateAssetStorageUnavailable("Private storage backend is incomplete.")
        if (
            getattr(storage, "is_private", False) is not True
            or getattr(storage, "is_durable", False) is not True
        ):
            raise PrivateAssetStorageUnavailable(
                "Production storage must explicitly declare private and durable access."
            )
        return storage

    if not settings.DEBUG:
        raise PrivateAssetStorageUnavailable("A durable private storage backend is required in production.")

    configured_root = Path(getattr(
        settings, "LEARNING_PRIVATE_ASSET_ROOT",
        settings.BASE_DIR / "private_learning_assets",
    ))
    if configured_root.is_symlink():
        raise PrivateAssetStorageUnavailable("The private asset root must not be a symlink.")
    root = configured_root.resolve()
    media_root = Path(settings.MEDIA_ROOT).resolve()
    if root == media_root or root in media_root.parents or media_root in root.parents:
        raise PrivateAssetStorageUnavailable("Private storage must not overlap public media storage.")
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
    except OSError as exc:
        raise PrivateAssetStorageUnavailable("Private storage directory is unavailable.") from exc
    return FileSystemStorage(
        location=str(root),
        base_url=None,
        file_permissions_mode=0o600,
        directory_permissions_mode=0o700,
    )


def scan_asset_bytes(content, suffix):
    """Return (state, scanned_at); missing/erroring scanners leave quarantine."""
    configured = (getattr(settings, "LEARNING_ASSET_SCANNER_BINARY", "") or "").strip()
    if not configured:
        return "quarantined", None
    if os.path.isabs(configured):
        binary = configured if os.path.isfile(configured) and os.access(configured, os.X_OK) else None
    else:
        binary = shutil.which(configured)
    if not binary:
        return "quarantined", None

    try:
        with tempfile.NamedTemporaryFile(prefix="learning-asset-", suffix=suffix) as temp:
            temp.write(content)
            temp.flush()
            result = subprocess.run(
                [binary, "--no-summary", "--", temp.name],
                check=False,
                capture_output=True,
                timeout=getattr(settings, "LEARNING_ASSET_SCANNER_TIMEOUT_SECONDS", 30),
                text=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        return "quarantined", None

    scanned_at = datetime.now(timezone.utc)
    if result.returncode == 0:
        return "clean", scanned_at
    if result.returncode == 1:
        return "infected", scanned_at
    return "quarantined", None
