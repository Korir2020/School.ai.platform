from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import BackgroundJob, SchoolAdminProfile
from .fee_permissions import get_fee_access_school_id


def _authorized(request, job):
    user = request.user
    if job.job_type == "fee_receipts":
        get_fee_access_school_id(user, school_id=job.school_id)
        return True
    if user.is_superuser:
        return True
    admin = SchoolAdminProfile.objects.filter(
        user=user, school_id=job.school_id,
    ).exists()
    if admin:
        return True
    return False


def _job_or_error(request, pk):
    job = BackgroundJob.objects.filter(pk=pk).first()
    if job is None:
        return None, Response({"detail": "Job not found."}, status=404)
    if not _authorized(request, job):
        return None, Response({"detail": "Job not found."}, status=404)
    return job, None


@api_view(["GET"])
def background_job_status(request, pk):
    job, error = _job_or_error(request, pk)
    if error:
        return error
    expired = bool(job.expires_at and job.expires_at <= timezone.now())
    return Response({
        "id": str(job.pk), "type": job.job_type, "status": job.status,
        "progress": job.progress, "total": job.total,
        "error": job.error if job.status == "failed" else "",
        "created_at": job.created_at,
        "download_url": (
            f"/api/jobs/{job.pk}/download/"
            if job.status == "completed" and job.artifact_name and not expired
            else None
        ),
        "expires_at": job.expires_at,
    })


@api_view(["GET"])
def background_job_download(request, pk):
    job, error = _job_or_error(request, pk)
    if error:
        return error
    if job.status != "completed" or not job.artifact_name:
        return Response({"detail": "The document is not available yet."}, status=409)
    if job.expires_at and job.expires_at <= timezone.now():
        return Response({"detail": "This document has expired."}, status=410)
    filename = Path(job.artifact_name).name
    if filename != job.artifact_name:
        return Response({"detail": "The document is not available."}, status=404)
    path = Path(settings.BACKGROUND_JOB_ROOT) / str(job.school_id) / str(job.pk) / filename
    try:
        handle = path.open("rb")
    except OSError:
        return Response({"detail": "The document is not available."}, status=404)
    return FileResponse(
        handle, as_attachment=True, filename=filename,
        content_type=job.content_type or "application/octet-stream",
    )
