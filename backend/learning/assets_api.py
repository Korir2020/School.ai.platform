"""Fail-closed lifecycle APIs for private learning-resource files."""

import hashlib
import io
import warnings
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .asset_storage import (
    PrivateAssetStorageUnavailable,
    get_private_asset_storage,
    scan_asset_bytes,
)
from .catalog_api import (
    _age_for_profile,
    _language_candidates,
    _requested_language,
    _resource_is_visible,
    _resource_queryset as _catalog_resource_queryset,
)
from .content_api import (
    _actor,
    _audit,
    _is_admin,
    _record_revision,
    _resource_queryset as _studio_resource_queryset,
)
from .models import LearningPrivateAsset, LearningResource
from .permissions import ActiveLearnerSelfService, SchoolContentAuthor
from .throttles import LearningAssetThrottle


MAX_ASSET_BYTES = 10 * 1024 * 1024
MAX_RESOURCE_ASSETS = 10
MAX_RESOURCE_ASSET_BYTES = 50 * 1024 * 1024
MAX_IMAGE_DIMENSION = 10000
MAX_IMAGE_PIXELS = 40000000
MAX_PDF_PAGES = 100
STORAGE_SUFFIXES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class AssetValidationError(ValueError):
    pass


class AssetTooLargeError(AssetValidationError):
    pass


def _read_upload(upload):
    if getattr(upload, "size", 0) > MAX_ASSET_BYTES:
        raise AssetTooLargeError("Each learning asset must be no larger than 10 MiB.")
    chunks = []
    total = 0
    while True:
        chunk = upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_ASSET_BYTES:
            raise AssetTooLargeError("Each learning asset must be no larger than 10 MiB.")
        chunks.append(chunk)
    if total == 0:
        raise AssetValidationError("The uploaded file is empty.")
    return b"".join(chunks)


def _sanitize_pdf(content):
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise AssetValidationError("Encrypted PDFs are not accepted.")
        if len(reader.pages) < 1 or len(reader.pages) > MAX_PDF_PAGES:
            raise AssetValidationError(f"PDFs must contain 1 to {MAX_PDF_PAGES} pages.")
        writer = PdfWriter()
        for page in reader.pages:
            # Rebuild only page content. Drop annotations, page actions and
            # catalog-level names/scripts/attachments by not cloning the catalog.
            for key in ("/AA", "/OpenAction", "/Annots", "/Metadata"):
                if key in page:
                    del page[key]
            writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        clean = output.getvalue()
    except AssetValidationError:
        raise
    except Exception as exc:
        raise AssetValidationError("The PDF is invalid or could not be safely decoded.") from exc
    if not clean.startswith(b"%PDF-") or len(clean) > MAX_ASSET_BYTES:
        raise AssetValidationError("The PDF could not be safely normalized within the file limit.")
    return clean


def _sanitize_image(content):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                image_format = source.format
                width, height = source.size
                frames = getattr(source, "n_frames", 1)
                if image_format not in {"PNG", "JPEG"}:
                    raise AssetValidationError("Only PNG and JPEG images are accepted.")
                if width < 1 or height < 1 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                    raise AssetValidationError("Image dimensions exceed the allowed limit.")
                if width * height > MAX_IMAGE_PIXELS:
                    raise AssetValidationError("Image pixel count exceeds the allowed limit.")
                if frames != 1:
                    raise AssetValidationError("Animated or multi-frame images are not accepted.")
                source.verify()
            with Image.open(io.BytesIO(content)) as source:
                source.load()
                if image_format == "JPEG":
                    normalized = source.convert("RGB")
                    options = {"quality": 90, "optimize": True, "progressive": False}
                else:
                    normalized = source.convert("RGBA" if "A" in source.getbands() else "RGB")
                    options = {"optimize": True}
                output = io.BytesIO()
                normalized.save(output, format=image_format, **options)
                clean = output.getvalue()
    except AssetValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise AssetValidationError("The image is invalid or exceeds safe decode limits.") from exc
    if not clean or len(clean) > MAX_ASSET_BYTES:
        raise AssetTooLargeError("The normalized image exceeds the 10 MiB file limit.")
    content_type = "image/jpeg" if image_format == "JPEG" else "image/png"
    return clean, content_type


def _normalize_upload(upload):
    original = _read_upload(upload)
    if original.startswith(b"%PDF-"):
        normalized = _sanitize_pdf(original)
        return normalized, "application/pdf", ".pdf"
    image, content_type = _sanitize_image(original)
    return image, content_type, STORAGE_SUFFIXES[content_type]


def _safe_asset_metadata(asset):
    return {
        "id": asset.pk,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "scan_state": asset.scan_state,
        "created_at": asset.created_at,
        "scanned_at": asset.scanned_at,
        "download_available": asset.scan_state == "clean" and asset.deleted_at is None,
    }


def _resource_for_author(request, resource_id, *, lock=False):
    query = LearningResource.objects.filter(
        pk=resource_id,
        scope="school",
        school_id=request.learning_content_actor.school_id,
    )
    if request.learning_content_role != "school_admin":
        query = query.filter(author=request.user)
    if lock:
        query = query.select_for_update()
    return query.first()


def _resource_is_editable(resource):
    return (
        resource is not None
        and resource.origin == "marian"
        and resource.status in {"draft", "changes_requested"}
        and resource.retired_at is None
    )


def _asset_limit_error(resource, incoming_size):
    current = resource.private_assets.exclude(scan_state="deleted")
    if current.count() >= MAX_RESOURCE_ASSETS:
        return f"A resource may have at most {MAX_RESOURCE_ASSETS} active attachments."
    total = sum(current.values_list("size_bytes", flat=True))
    if total + incoming_size > MAX_RESOURCE_ASSET_BYTES:
        return "The combined active attachment limit for this resource is 50 MiB."
    return None


def _private_file_response(storage, asset):
    try:
        stream = storage.open(asset.storage_name, "rb")
    except FileNotFoundError:
        return None, False
    except Exception:
        return None, True
    filename = f"learning-resource-{asset.resource_id}-asset-{asset.pk}{STORAGE_SUFFIXES[asset.content_type]}"
    response = FileResponse(
        stream,
        as_attachment=True,
        filename=filename,
        content_type="application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "DENY"
    response["X-Download-Options"] = "noopen"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["Referrer-Policy"] = "no-referrer"
    return response, False


def _advance_asset_scan_state(request, asset_id, state, scanned_at):
    if state not in {"clean", "infected"} or scanned_at is None:
        return
    with transaction.atomic():
        resource_id = LearningPrivateAsset.objects.filter(
            pk=asset_id, scan_state="quarantined", deleted_at__isnull=True,
        ).values_list("resource_id", flat=True).first()
        if resource_id is None:
            return
        resource = LearningResource.objects.select_for_update().filter(pk=resource_id).first()
        if resource is None:
            return
        asset = LearningPrivateAsset.objects.select_for_update().filter(
            pk=asset_id, resource_id=resource_id,
            scan_state="quarantined", deleted_at__isnull=True,
        ).first()
        if asset is None:
            return
        asset.scan_state = state
        asset.scanned_at = scanned_at
        asset.save(update_fields=["scan_state", "scanned_at"])
        resource.version += 1
        resource.save(update_fields=["version", "updated_at"])
        _record_revision(resource, request.user)
        _audit(
            request, resource, "resource_asset_scan_completed",
            asset_id=asset.pk, scan_state=state,
        )


@api_view(["GET", "POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([LearningAssetThrottle])
def studio_resource_assets(request, resource_id):
    if request.query_params:
        return Response({"detail": "Asset operations do not accept query parameters."}, status=400)

    resource = _studio_resource_queryset(request).filter(pk=resource_id).first()
    if resource is None:
        return Response({"detail": "Learning resource not found."}, status=404)
    if request.method == "GET":
        rows = resource.private_assets.exclude(scan_state="deleted").order_by("created_at", "id")
        return Response({"results": [_safe_asset_metadata(row) for row in rows]})

    if (
        set(request.data.keys()) != {"file"}
        or set(request.FILES.keys()) != {"file"}
        or len(request.FILES.getlist("file")) != 1
    ):
        return Response({"detail": "Upload exactly one file field named 'file'."}, status=400)
    if not _resource_is_editable(resource):
        return Response({"detail": "Attachments may be changed only on an unsubmitted school draft."}, status=409)
    try:
        normalized, content_type, suffix = _normalize_upload(request.FILES.getlist("file")[0])
    except AssetTooLargeError as exc:
        return Response({"code": "asset_too_large", "detail": str(exc)}, status=413)
    except AssetValidationError as exc:
        return Response({"detail": str(exc)}, status=400)

    try:
        storage = get_private_asset_storage()
        storage_name = storage.save(
            f"learning-assets/quarantine/{uuid4().hex}{suffix}",
            ContentFile(normalized),
        )
    except Exception:
        return Response({"code": "private_asset_storage_unavailable", "detail": "Private file storage is not configured or is unavailable."}, status=503)

    asset = None
    try:
        with transaction.atomic():
            locked = _resource_for_author(request, resource_id, lock=True)
            if locked is None:
                rejected = Response({"detail": "Learning resource not found."}, status=404)
            elif not _resource_is_editable(locked):
                rejected = Response({"detail": "Attachments may be changed only on an unsubmitted school draft."}, status=409)
            else:
                limit_error = _asset_limit_error(locked, len(normalized))
                if limit_error:
                    rejected = Response({"detail": limit_error}, status=409)
                else:
                    asset = LearningPrivateAsset.objects.create(
                        resource=locked,
                        storage_name=storage_name,
                        content_type=content_type,
                        size_bytes=len(normalized),
                        sha256=hashlib.sha256(normalized).hexdigest(),
                        scan_state="quarantined",
                        uploaded_by=request.user,
                    )
                    locked.version += 1
                    locked.save(update_fields=["version", "updated_at"])
                    _record_revision(locked, request.user)
                    _audit(
                        request, locked, "resource_asset_uploaded",
                        asset_id=asset.pk, scan_state="quarantined", size_bytes=asset.size_bytes,
                    )
                    rejected = None
    except Exception:
        try:
            storage.delete(storage_name)
        except Exception:
            pass
        raise

    if rejected is not None:
        try:
            storage.delete(storage_name)
        except Exception:
            pass
        return rejected

    # Quarantine metadata is committed before scanning. A crash leaves a tracked,
    # inaccessible row rather than an unreferenced file or implicitly clean asset.
    try:
        scan_state, scanned_at = scan_asset_bytes(normalized, suffix)
    except Exception:
        scan_state, scanned_at = "quarantined", None
    _advance_asset_scan_state(request, asset.pk, scan_state, scanned_at)
    asset.refresh_from_db()
    if asset.deleted_at is not None:
        return Response({"detail": "The learning asset was deleted during scanning."}, status=409)
    return Response(_safe_asset_metadata(asset), status=201)


@api_view(["GET"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningAssetThrottle])
def studio_resource_asset_download(request, resource_id, asset_id):
    if request.query_params:
        return Response({"detail": "Asset downloads do not accept query parameters."}, status=400)
    resource = _resource_for_author(request, resource_id)
    if resource is None:
        return Response({"detail": "Learning resource not found."}, status=404)
    asset = resource.private_assets.filter(
        pk=asset_id, scan_state="clean", deleted_at__isnull=True,
    ).first()
    if asset is None:
        return Response({"detail": "Learning asset not found."}, status=404)
    try:
        storage = get_private_asset_storage()
    except PrivateAssetStorageUnavailable:
        return Response({"code": "private_asset_storage_unavailable", "detail": "Private file storage is unavailable."}, status=503)
    response, unavailable = _private_file_response(storage, asset)
    if unavailable:
        return Response({"code": "private_asset_storage_unavailable", "detail": "Private file storage is unavailable."}, status=503)
    if response is None:
        return Response({"detail": "Learning asset not found."}, status=404)
    _audit(request, resource, "resource_asset_review_downloaded", asset_id=asset.pk)
    return response


@api_view(["DELETE"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningAssetThrottle])
def studio_resource_asset_detail(request, resource_id, asset_id):
    if request.query_params or request.body:
        return Response({"detail": "Asset deletion does not accept query parameters or a body."}, status=400)
    deleted_name = None
    with transaction.atomic():
        resource = _resource_for_author(request, resource_id, lock=True)
        if resource is None:
            return Response({"detail": "Learning resource not found."}, status=404)
        asset = resource.private_assets.select_for_update().filter(pk=asset_id).first()
        if asset is None:
            return Response({"detail": "Learning asset not found."}, status=404)
        if asset.deleted_at is None:
            draft_delete_allowed = _resource_is_editable(resource)
            archived_admin_delete_allowed = (
                resource.status == "archived" and _is_admin(request)
            )
            if not (draft_delete_allowed or archived_admin_delete_allowed):
                return Response({
                    "detail": "Delete attachments only on a draft; a full school administrator must archive other content before cleanup."
                }, status=409)
            asset.scan_state = "deleted"
            asset.deleted_at = timezone.now()
            asset.save(update_fields=["scan_state", "deleted_at"])
            resource.version += 1
            resource.save(update_fields=["version", "updated_at"])
            _record_revision(resource, request.user)
            _audit(request, resource, "resource_asset_deleted", asset_id=asset.pk)
        deleted_name = asset.storage_name

    # Revoke access in the DB before deleting bytes. A retry of this DELETE
    # retries physical cleanup if a storage outage interrupted the first attempt.
    try:
        storage = get_private_asset_storage()
        storage.delete(deleted_name)
    except Exception:
        return Response({
            "code": "asset_cleanup_pending",
            "detail": "Access has been revoked; retry deletion when private storage is available to finish cleanup.",
        }, status=503)
    return Response(status=204)


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningAssetThrottle])
def catalog_resource_asset_download(request, resource_id, asset_id):
    if set(request.query_params) - {"lang"}:
        return Response({"detail": "Unsupported asset filter."}, status=400)
    profile = request.learning_profile
    language, error = _requested_language(request, profile)
    if error:
        return error
    age = _age_for_profile(profile)
    candidates = _language_candidates(language)
    resource = _catalog_resource_queryset(profile, age, candidates).filter(pk=resource_id).first()
    if resource is None or not _resource_is_visible(profile, resource, age, candidates):
        return Response({"detail": "Learning asset not found."}, status=404)
    asset = resource.private_assets.filter(
        pk=asset_id, scan_state="clean", deleted_at__isnull=True,
    ).first()
    if asset is None:
        return Response({"detail": "Learning asset not found."}, status=404)
    try:
        storage = get_private_asset_storage()
    except PrivateAssetStorageUnavailable:
        return Response({"code": "private_asset_storage_unavailable", "detail": "Private file storage is unavailable."}, status=503)
    response, unavailable = _private_file_response(storage, asset)
    if unavailable:
        return Response({"code": "private_asset_storage_unavailable", "detail": "Private file storage is unavailable."}, status=503)
    if response is None:
        return Response({"detail": "Learning asset not found."}, status=404)
    return response
