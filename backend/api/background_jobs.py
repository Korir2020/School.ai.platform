"""Durable, school-scoped background processing for large document batches.

The database row is the queue. Run ``python manage.py run_background_jobs`` as
an independent process; do not start a thread from a web worker. In production,
web and worker processes must share ``DJANGO_BACKGROUND_JOB_ROOT`` (or configure
a shared private volume). Artifacts are never placed in MEDIA_ROOT or served
without an authenticated tenant check.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import zipfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from schools.models import (
    BackgroundJob, ExamResult, FeePayment, Performance, Student, Term,
)
from .subject_registration_rules import registered_marks

logger = logging.getLogger(__name__)
MAX_DOCUMENT_BATCH = 5000
ASYNC_DOCUMENT_THRESHOLD = 50
JOB_TTL_DAYS = 7
STALE_JOB_MINUTES = 15


def enqueue_document_job(*, school, user, job_type, payload, total):
    if job_type not in {"report_cards", "fee_receipts"}:
        raise ValueError("Unsupported document job type.")
    if total < 1 or total > MAX_DOCUMENT_BATCH:
        raise ValueError("A document job must contain between 1 and 5,000 records.")
    return BackgroundJob.objects.create(
        school=school, requested_by=user, job_type=job_type,
        payload=payload, total=total,
    )


def _job_dir(job):
    return Path(settings.BACKGROUND_JOB_ROOT) / str(job.school_id) / str(job.pk)


def _safe_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return (cleaned or "document")[:100]


def _progress(job, count):
    now = timezone.now()
    BackgroundJob.objects.filter(pk=job.pk, status="running").update(
        progress=count, heartbeat_at=now, updated_at=now,
    )


def _merge_pdfs(pdf_paths, output_path):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for path in pdf_paths:
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    writer.write(str(output_path))


def _make_artifact(job, documents, label):
    """Write an individual ZIP, merged PDF, or both to a private job folder."""
    fmt = job.payload.get("format", "combined")
    if fmt not in {"combined", "zip", "both"}:
        raise ValueError("Unsupported document format.")
    target_dir = _job_dir(job)
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target_dir, 0o700)

    if fmt == "zip":
        filename = f"{label}.zip"
        output = target_dir / filename
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for arcname, path in documents:
                archive.write(path, arcname=arcname)
        os.chmod(output, 0o600)
        return filename, "application/zip"

    combined_path = target_dir / f"{label}.pdf"
    _merge_pdfs([path for _, path in documents], combined_path)
    os.chmod(combined_path, 0o600)
    if fmt == "combined":
        return combined_path.name, "application/pdf"

    filename = f"{label}-both.zip"
    output = target_dir / filename
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(combined_path, arcname=combined_path.name)
        for arcname, path in documents:
            archive.write(path, arcname=arcname)
    os.chmod(output, 0o600)
    return filename, "application/zip"


def _generate_report_cards(job):
    from . import documents

    if documents.colors is None:
        raise RuntimeError("PDF generation dependencies are not installed.")
    term = Term.objects.select_related("academic_year", "academic_year__school").filter(
        pk=job.payload.get("term_id"),
        academic_year__school_id=job.school_id,
    ).first()
    if term is None:
        raise ValueError("The selected term is no longer available in this school.")
    ids = job.payload.get("student_ids")
    if not isinstance(ids, list) or len(ids) != job.total:
        raise ValueError("The report-card selection is invalid.")
    eligible = registered_marks(
        Performance.objects.filter(
            term=term, status__in=["approved", "locked"], student_id__in=ids,
        ), term.academic_year,
    ).values_list("student_id", flat=True).distinct()
    students = list(
        Student.objects.filter(pk__in=ids, school_id=job.school_id)
        .filter(pk__in=eligible).select_related("school")
        .order_by("last_name", "first_name", "id")
    )
    if len(students) != job.total:
        raise ValueError("A selected learner is no longer eligible for this report batch.")

    folder = _job_dir(job)
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    work_dir = folder / "work"
    work_dir.mkdir(mode=0o700)
    payloads = documents._report_payloads(students, term)
    pdfs = []
    for index, student in enumerate(students, start=1):
        pdf_path = work_dir / f"report-{index:05d}.pdf"
        pdf_path.write_bytes(documents._report_pdf(
            student, term, term.academic_year.school,
            payload=payloads[student.id],
        ))
        pdfs.append((f"report-card-{_safe_name(student.admission_number)}.pdf", pdf_path))
        if index % 10 == 0 or index == job.total:
            _progress(job, index)
    return _make_artifact(job, pdfs, "report-cards")


def _generate_fee_receipts(job):
    from . import documents

    if documents.colors is None:
        raise RuntimeError("PDF generation dependencies are not installed.")
    ids = job.payload.get("payment_ids")
    if not isinstance(ids, list) or len(ids) != job.total:
        raise ValueError("The receipt selection is invalid.")
    payments = list(
        FeePayment.objects.filter(
            pk__in=ids, student_fee__student__school_id=job.school_id,
        ).select_related(
            "student_fee__student__school", "student_fee__fee_structure",
        ).order_by("id")
    )
    if len(payments) != job.total:
        raise ValueError("A selected payment is no longer available in this school.")

    folder = _job_dir(job)
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    work_dir = folder / "work"
    work_dir.mkdir(mode=0o700)
    pdfs = []
    for index, payment in enumerate(payments, start=1):
        pdf_path = work_dir / f"receipt-{index:05d}.pdf"
        pdf_path.write_bytes(documents._receipt_pdf(
            payment, payment.student_fee.student.school,
        ))
        pdfs.append((f"receipt-{_safe_name(documents._receipt_number(payment))}.pdf", pdf_path))
        if index % 10 == 0 or index == job.total:
            _progress(job, index)
    return _make_artifact(job, pdfs, "fee-receipts")


def _claim_one():
    now = timezone.now()
    stale_before = now - timedelta(minutes=STALE_JOB_MINUTES)
    with transaction.atomic():
        job = (BackgroundJob.objects.select_for_update(skip_locked=True)
               .filter(Q(status="queued") | Q(
                   status="running",
               ) & (Q(heartbeat_at__lt=stale_before) | Q(heartbeat_at__isnull=True)))
               .order_by("created_at", "id").first())
        if job is None:
            return None
        job.status = "running"
        job.started_at = now
        job.heartbeat_at = now
        job.attempts += 1
        job.progress = 0
        job.error = ""
        job.save(update_fields=[
            "status", "started_at", "heartbeat_at", "attempts", "progress",
            "error", "updated_at",
        ])
        return job


def process_one_job():
    """Claim and run one durable job; return False when the queue is empty."""
    job = _claim_one()
    if job is None:
        return False
    try:
        if job.job_type == "report_cards":
            artifact, content_type = _generate_report_cards(job)
        elif job.job_type == "fee_receipts":
            artifact, content_type = _generate_fee_receipts(job)
        else:
            raise ValueError("Unsupported background job type.")
        now = timezone.now()
        BackgroundJob.objects.filter(pk=job.pk, status="running").update(
            status="completed", progress=job.total, artifact_name=artifact,
            content_type=content_type, error="", finished_at=now,
            heartbeat_at=now, expires_at=now + timedelta(days=JOB_TTL_DAYS),
            updated_at=now,
        )
    except Exception as exc:  # persisted failure; worker loop remains alive
        logger.exception("Background document job %s failed", job.pk)
        now = timezone.now()
        BackgroundJob.objects.filter(pk=job.pk, status="running").update(
            status="failed", error=(str(exc) or exc.__class__.__name__)[:2000],
            finished_at=now, heartbeat_at=now, updated_at=now,
        )
    return True


def cleanup_expired_artifacts():
    now = timezone.now()
    root = Path(settings.BACKGROUND_JOB_ROOT)
    jobs = BackgroundJob.objects.filter(
        expires_at__lte=now,
    ).exclude(artifact_name="")
    cleaned = 0
    for job in jobs.iterator(chunk_size=100):
        folder = root / str(job.school_id) / str(job.pk)
        shutil.rmtree(folder, ignore_errors=True)
        BackgroundJob.objects.filter(pk=job.pk).update(
            artifact_name="", content_type="", expires_at=None,
            updated_at=now,
        )
        cleaned += 1
    return cleaned
