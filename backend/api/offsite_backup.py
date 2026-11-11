"""Encrypted, immutable off-site backup sets. Separate from the redacted JSON export."""
import base64
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from threading import Event, Thread
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from schools.models import OffsiteBackupRun
from .permissions import IsSuperAdmin


def configured():
    required = ("OFFSITE_S3_BUCKET", "OFFSITE_S3_ACCESS_KEY", "OFFSITE_S3_SECRET_KEY",
                "BACKUP_ENCRYPTION_KEY", "BACKUP_MANIFEST_HMAC_KEY")
    return all(os.environ.get(k) for k in required)


def _secret(name, *, hex_ok=False):
    value = os.environ.get(name, "")
    if hex_ok and len(value) == 64:
        try:
            result = bytes.fromhex(value)
            if len(result) == 32:
                return result
        except ValueError:
            pass
    try:
        result = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise RuntimeError(f"{name} must be base64-encoded key material.") from exc
    return result


def _keys():
    enc = _secret("BACKUP_ENCRYPTION_KEY", hex_ok=True)
    mac = _secret("BACKUP_MANIFEST_HMAC_KEY")
    if len(enc) != 32:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256).")
    if len(mac) < 32:
        raise RuntimeError("BACKUP_MANIFEST_HMAC_KEY must decode to at least 32 bytes.")
    return enc, mac


def _client():
    import boto3
    endpoint = os.environ.get("OFFSITE_S3_ENDPOINT_URL") or None
    if endpoint and not endpoint.lower().startswith("https://") and not settings.DEBUG:
        raise RuntimeError("OFFSITE_S3_ENDPOINT_URL must use HTTPS outside debug mode.")
    return boto3.client(
        "s3", endpoint_url=endpoint,
        region_name=os.environ.get("OFFSITE_S3_REGION", "us-east-1"),
        aws_access_key_id=os.environ["OFFSITE_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["OFFSITE_S3_SECRET_KEY"],
    )


def _retry(call):
    tries = max(1, min(6, int(os.environ.get("BACKUP_RETRY_ATTEMPTS", "3"))))
    base = max(0.1, min(60.0, float(os.environ.get("BACKUP_RETRY_BASE_SECONDS", "1"))))
    for attempt in range(tries):
        try:
            return call()
        except Exception:
            if attempt + 1 == tries:
                raise
            time.sleep(min(60.0, base * (2 ** attempt)))


def _sha_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_object(client, bucket, key, destination):
    def attempt():
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            with open(destination, "wb") as out:
                shutil.copyfileobj(body, out, 1024 * 1024)
        except Exception:
            Path(destination).unlink(missing_ok=True)
            raise
        finally:
            body.close()
        return destination
    return _retry(attempt)


def _read_object(client, bucket, key):
    def attempt():
        body = client.get_object(Bucket=bucket, Key=key)["Body"]
        try:
            return body.read()
        finally:
            body.close()
    return _retry(attempt)


def _encrypt_file(source, target, key, purpose):
    nonce = os.urandom(12)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(purpose.encode("ascii"))
    with open(source, "rb") as src, open(target, "wb") as dst:
        dst.write(nonce)
        for block in iter(lambda: src.read(1024 * 1024), b""):
            dst.write(encryptor.update(block))
        dst.write(encryptor.finalize())
        dst.write(encryptor.tag)
    return {"ciphertext_sha256": _sha_file(target), "plaintext_sha256": _sha_file(source),
            "bytes": os.path.getsize(source)}


def _decrypt_file(source, target, key, purpose):
    size = os.path.getsize(source)
    if size < 28:
        raise RuntimeError("Encrypted backup object is truncated.")
    with open(source, "rb") as src:
        nonce = src.read(12)
        src.seek(size - 16)
        tag = src.read(16)
        src.seek(12)
        remaining = size - 28
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(purpose.encode("ascii"))
        try:
            with open(target, "wb") as dst:
                while remaining:
                    block = src.read(min(1024 * 1024, remaining))
                    if not block:
                        raise RuntimeError("Encrypted backup object is truncated.")
                    remaining -= len(block)
                    dst.write(decryptor.update(block))
                dst.write(decryptor.finalize())
        except Exception:
            Path(target).unlink(missing_ok=True)
            raise
    return _sha_file(target)


_EXCLUDED_TABLE_DATA = (
    "django_session", "token_blacklist_outstandingtoken",
    "token_blacklist_blacklistedtoken", "schools_superadminsecurity",
)


def _sanitize_sqlite_snapshot(path):
    """Remove transient sessions/revoked-token rows and MFA secrets from the copy only."""
    db = sqlite3.connect(path)
    try:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in _EXCLUDED_TABLE_DATA:
            if table in tables:
                db.execute(f'DELETE FROM "{table}"')
        db.commit()
    finally:
        db.close()


def _make_db_dump(path):
    engine = settings.DATABASES["default"]["ENGINE"]
    if engine.endswith("sqlite3"):
        connection.ensure_connection()
        target = sqlite3.connect(path)
        try:
            connection.connection.backup(target)
            target.commit()
        finally:
            target.close()
        _sanitize_sqlite_snapshot(path)
        return "sqlite"
    if engine.endswith("postgresql"):
        db = settings.DATABASES["default"]
        args = [os.environ.get("PG_DUMP_BIN", "pg_dump"), "--format=custom", "--no-owner",
                "--no-privileges", "--no-password",
                "--file", path, "--dbname", str(db["NAME"])]
        for table in _EXCLUDED_TABLE_DATA:
            args.append(f"--exclude-table-data={table}")
        for flag, value in (("--host", db.get("HOST")), ("--port", db.get("PORT")),
                            ("--username", db.get("USER"))):
            if value:
                args.extend((flag, str(value)))
        env = os.environ.copy()
        if db.get("PASSWORD"):
            env["PGPASSWORD"] = str(db["PASSWORD"])
        env.setdefault("PGSSLMODE", os.environ.get("PGSSLMODE", "prefer"))
        subprocess.run(args, check=True, env=env, capture_output=True, text=True, timeout=3600)
        return "postgresql-custom"
    raise RuntimeError(f"Unsupported database engine for off-site backup: {engine}")


def _make_media_archive(path):
    root = Path(settings.MEDIA_ROOT)
    with tarfile.open(path, "w:gz") as archive:
        if root.exists():
            for base, dirs, files in os.walk(root, followlinks=False):
                base_path = Path(base)
                dirs[:] = [d for d in dirs if not (base_path / d).is_symlink()]
                for item in dirs + files:
                    full = base_path / item
                    if full.is_symlink():
                        raise RuntimeError("MEDIA_ROOT contains a symlink; refusing an ambiguous backup.")
                    archive.add(full, arcname=Path("media") / full.relative_to(root), recursive=False)


def _sign_manifest(doc, mac_key):
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    signed = dict(doc)
    signed["hmac_sha256"] = hmac.new(mac_key, payload, hashlib.sha256).hexdigest()
    return signed


def verify_manifest(doc, mac_key):
    if not isinstance(doc, dict) or not isinstance(doc.get("hmac_sha256"), str):
        raise RuntimeError("Backup manifest is missing its HMAC.")
    signature = doc["hmac_sha256"]
    unsigned = {key: value for key, value in doc.items() if key != "hmac_sha256"}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(mac_key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise RuntimeError("Backup manifest HMAC verification failed.")
    if unsigned.get("format") != "marian-offsite-backup" or unsigned.get("version") != 1:
        raise RuntimeError("Unsupported off-site backup manifest format.")
    return unsigned


def _upload_and_verify(run, folder):
    enc_key, mac_key = _keys()
    client = _client()
    bucket = os.environ["OFFSITE_S3_BUCKET"]
    prefix = os.environ.get("OFFSITE_S3_PREFIX", "marian-backups").strip("/")
    # Every attempt writes a new set; a retry never overwrites a prior partial set.
    base = f"{prefix}/{run.id}/{uuid4()}"
    plain_db = os.path.join(folder, "database.dump")
    plain_media = os.path.join(folder, "media.tar.gz")
    engine = _make_db_dump(plain_db)
    _make_media_archive(plain_media)
    encrypted = {}
    for kind, source in (("database", plain_db), ("media", plain_media)):
        local = os.path.join(folder, f"{kind}.aesgcm")
        info = _encrypt_file(source, local, enc_key, kind)
        key = f"{base}/{kind}.aesgcm"
        _retry(lambda p=local, k=key: client.upload_file(p, bucket, k,
               ExtraArgs={"ContentType": "application/octet-stream"}))
        encrypted[kind] = {"key": key, **info}
    manifest = _sign_manifest({
        "format": "marian-offsite-backup", "version": 1, "run_id": str(run.id),
        "created_at": timezone.now().isoformat(), "database_engine": engine,
        "encryption": "AES-256-GCM", "media_root_included": True,
        "objects": encrypted,
    }, mac_key)
    manifest_key = f"{base}/manifest.json"
    manifest_path = os.path.join(folder, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, sort_keys=True, separators=(",", ":"))
    _retry(lambda: client.upload_file(manifest_path, bucket, manifest_key,
           ExtraArgs={"ContentType": "application/json"}))

    # Read back all remote bytes; verify signature, ciphertext, decryption and plaintext digest.
    readback = _read_object(client, bucket, manifest_key)
    remote_manifest = verify_manifest(json.loads(readback), mac_key)
    if remote_manifest != {k: v for k, v in manifest.items() if k != "hmac_sha256"}:
        raise RuntimeError("Remote manifest read-back differs from the uploaded manifest.")
    for kind, entry in encrypted.items():
        temp_cipher = os.path.join(folder, f"{kind}.readback")
        _download_object(client, bucket, entry["key"], temp_cipher)
        if _sha_file(temp_cipher) != entry["ciphertext_sha256"]:
            raise RuntimeError(f"Remote {kind} ciphertext SHA-256 verification failed.")
        decoded = os.path.join(folder, f"{kind}.verified")
        if _decrypt_file(temp_cipher, decoded, enc_key, kind) != entry["plaintext_sha256"]:
            raise RuntimeError(f"Remote {kind} plaintext SHA-256 verification failed.")
    _apply_retention(client, bucket, prefix)
    return encrypted, manifest_key, {
        "database_engine": engine, "media_included": True,
        "remote_readback_verified": True,
        "database_bytes": encrypted["database"]["bytes"],
        "media_bytes": encrypted["media"]["bytes"],
        "ciphertext_bytes": sum(os.path.getsize(os.path.join(folder, f"{kind}.aesgcm"))
                                 for kind in encrypted),
        "manifest_sha256": _sha_file(manifest_path),
    }


def _apply_retention(client, bucket, prefix):
    days = max(1, min(3650, int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))))
    cutoff = timezone.now() - timedelta(days=days)
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix + "/"):
        obsolete = [{"Key": x["Key"]} for x in page.get("Contents", [])
                    if x["LastModified"] < cutoff]
        if obsolete:
            _retry(lambda objects=obsolete: client.delete_objects(
                Bucket=bucket, Delete={"Objects": objects, "Quiet": True}))


def process_run(run_id, lease_token):
    lease_seconds = max(60, int(os.environ.get("BACKUP_LEASE_SECONDS", "7200")))
    stop = Event()

    def refresh_lease():
        from django.db import close_old_connections
        interval = max(20, min(300, lease_seconds // 3))
        while not stop.wait(interval):
            close_old_connections()
            renewed = OffsiteBackupRun.objects.filter(
                pk=run_id, lease_token=lease_token, status="running",
            ).update(lease_expires_at=timezone.now() + timedelta(seconds=lease_seconds))
            close_old_connections()
            if not renewed:
                return

    heartbeat = Thread(target=refresh_lease, name=f"backup-lease-{run_id}", daemon=True)
    heartbeat.start()
    try:
        run = OffsiteBackupRun.objects.get(pk=run_id, lease_token=lease_token, status="running")
        with tempfile.TemporaryDirectory(prefix="marian-offsite-") as folder:
            archive_keys, manifest_key, result = _upload_and_verify(run, folder)
        with transaction.atomic():
            locked = OffsiteBackupRun.objects.select_for_update().filter(
                pk=run_id, lease_token=lease_token, status="running",
            ).first()
            if locked is None:
                return False
            locked.status = "succeeded"
            locked.finished_at = timezone.now()
            locked.lease_expires_at = None
            locked.error = ""
            locked.archive_keys = archive_keys
            locked.manifest_key = manifest_key
            locked.result = result
            locked.save(update_fields=["status", "finished_at", "lease_expires_at", "error",
                                       "archive_keys", "manifest_key", "result"])
        return "succeeded"
    except Exception as exc:
        with transaction.atomic():
            locked = OffsiteBackupRun.objects.select_for_update().filter(
                pk=run_id, lease_token=lease_token, status="running",
            ).first()
            if locked is None:
                return False
            locked.error = f"{type(exc).__name__}: {exc}"[:4000]
            locked.lease_expires_at = None
            max_attempts = max(1, min(6, int(os.environ.get("BACKUP_RETRY_ATTEMPTS", "3"))))
            if locked.attempts < max_attempts:
                base = max(1, min(3600, int(os.environ.get("BACKUP_RETRY_BASE_SECONDS", "1"))))
                locked.status = "queued"
                locked.retry_after = timezone.now() + timedelta(
                    seconds=min(3600, base * (2 ** max(0, locked.attempts - 1))),
                )
                locked.finished_at = None
            else:
                locked.status = "failed"
                locked.finished_at = timezone.now()
                locked.retry_after = None
            outcome = locked.status
            locked.save(update_fields=["status", "finished_at", "lease_expires_at",
                                       "retry_after", "error"])
        return outcome
    finally:
        stop.set()
        heartbeat.join(timeout=2)


def claim_next_run():
    now = timezone.now()
    with transaction.atomic():
        run = OffsiteBackupRun.objects.select_for_update().filter(
            status="queued", retry_after__isnull=True,
        ).order_by("created_at").first()
        if run is None:
            run = OffsiteBackupRun.objects.select_for_update().filter(
                status="queued", retry_after__lte=now,
            ).order_by("created_at").first()
        if run is None:
            run = OffsiteBackupRun.objects.select_for_update().filter(
                status="running", lease_expires_at__lt=now,
            ).order_by("created_at").first()
        if run is None:
            return None
        token = uuid4()
        run.status = "running"
        run.lease_token = token
        run.lease_expires_at = now + timedelta(seconds=max(60, int(os.environ.get("BACKUP_LEASE_SECONDS", "7200"))))
        run.retry_after = None
        run.started_at = run.started_at or now
        run.finished_at = None
        run.attempts += 1
        run.save(update_fields=["status", "lease_token", "lease_expires_at", "retry_after",
                                "started_at", "finished_at", "attempts"])
        return run.id, token


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def offsite_backup_status(request):
    is_configured = configured()
    latest = OffsiteBackupRun.objects.first()
    latest_success = OffsiteBackupRun.objects.filter(status="succeeded").first()
    schedule_declared = os.environ.get("BACKUP_SCHEDULER_DECLARED", "false").lower() == "true"
    warnings = []
    if not is_configured:
        warnings.append("Off-site storage and encryption keys are not fully configured.")
    if not schedule_declared:
        warnings.append("No external backup schedule has been declared; queued jobs will not run automatically.")
    verified_at = (latest_success.finished_at if latest_success
                   and latest_success.result.get("remote_readback_verified") else None)
    storage_usage = None
    if is_configured:
        try:
            client = _client()
            bucket = os.environ["OFFSITE_S3_BUCKET"]
            prefix = os.environ.get("OFFSITE_S3_PREFIX", "marian-backups").strip("/") + "/"
            storage_usage = sum(item.get("Size", 0) for page in client.get_paginator("list_objects_v2").paginate(
                Bucket=bucket, Prefix=prefix) for item in page.get("Contents", []))
        except Exception as exc:
            warnings.append(f"Could not measure off-site storage: {type(exc).__name__}.")
    retention_days = max(1, min(3650, int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))))
    restore_drill = os.environ.get("BACKUP_LAST_RESTORE_DRILL_AT") or None
    operational = bool(is_configured and storage_usage is not None and schedule_declared
                       and verified_at and restore_drill)
    return Response({
        "configured": is_configured,
        "operational": operational,
        "automatic_schedule_configured": schedule_declared,
        "last_success": verified_at,
        "last_remote_readback_verified_at": verified_at,
        "next_scheduled_at": os.environ.get("BACKUP_NEXT_SCHEDULED_AT") or None,
        "storage_usage_bytes": storage_usage,
        "retention_days": retention_days,
        "last_restore_drill": restore_drill,
        "setup_warnings": warnings,
        "latest": _serialize(latest) if latest else None,
        "storage_type": "S3-compatible" if is_configured else None,
    })


def _serialize(run):
    return {"id": str(run.id), "status": run.status, "requested_by": run.requested_by_id,
            "created_at": run.created_at, "started_at": run.started_at,
            "finished_at": run.finished_at, "attempts": run.attempts, "error": run.error,
            "manifest_key": run.manifest_key, "result": run.result}


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def offsite_backup_history(request):
    try:
        limit = max(1, min(100, int(request.query_params.get("limit", "20"))))
    except ValueError:
        return Response({"detail": "limit must be between 1 and 100."}, status=400)
    return Response({"results": [_serialize(x) for x in OffsiteBackupRun.objects.all()[:limit]]})


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def offsite_backup_trigger(request):
    run = OffsiteBackupRun.objects.create(requested_by=request.user)
    return Response(_serialize(run), status=202)


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def offsite_backup_retry(request, pk):
    with transaction.atomic():
        run = OffsiteBackupRun.objects.select_for_update().filter(pk=pk).first()
        if not run:
            return Response({"detail": "Backup run not found."}, status=404)
        if run.status != "failed":
            return Response({"detail": "Only failed backup runs can be retried."}, status=409)
        run.status, run.retry_after, run.finished_at = "queued", None, None
        run.error = ""
        run.save(update_fields=["status", "retry_after", "finished_at", "error"])
    return Response(_serialize(run), status=202)


# Kept for shared callers and explicit operator diagnostics.
class BackupConfigurationError(RuntimeError):
    pass


def require_configured():
    if not configured():
        raise BackupConfigurationError("Off-site backup is not configured; set S3 credentials, bucket, AES key and manifest HMAC key.")


def download_manifest(run_id):
    require_configured()
    run = OffsiteBackupRun.objects.get(pk=run_id, status="succeeded")
    _, mac_key = _keys()
    client = _client()
    data = _read_object(client, os.environ["OFFSITE_S3_BUCKET"], run.manifest_key)
    manifest = verify_manifest(json.loads(data), mac_key)
    if manifest.get("run_id") != str(run.id):
        raise RuntimeError("Backup manifest run ID does not match the requested run.")
    return run, manifest, client


def download_and_decrypt(run_id, folder):
    run, manifest, client = download_manifest(run_id)
    enc_key, _ = _keys()
    bucket = os.environ["OFFSITE_S3_BUCKET"]
    result = {}
    for kind, item in manifest["objects"].items():
        encrypted = os.path.join(folder, f"{kind}.aesgcm")
        _download_object(client, bucket, item["key"], encrypted)
        if _sha_file(encrypted) != item["ciphertext_sha256"]:
            raise RuntimeError(f"{kind} ciphertext checksum failed.")
        clear = os.path.join(folder, f"{kind}.plain")
        if _decrypt_file(encrypted, clear, enc_key, kind) != item["plaintext_sha256"]:
            raise RuntimeError(f"{kind} plaintext checksum failed.")
        result[kind] = clear
    return run, manifest, result
