"""Durable immutable archives for issued, published learner reports."""
import hashlib
import re

from django.db import IntegrityError, transaction
from django.http import HttpResponse

from marian_reports.assembler import sign
from schools.models import PublishedReportArtifact


def find_published_report(school_id, exam_id, student_id):
    return PublishedReportArtifact.objects.filter(
        school_id=school_id, exam_id=exam_id, student_id=student_id,
    ).first()


def archive_published_report(*, exam, student, report_no, result_mode, pdf,
                             source_digest=""):
    """Create the first archive for a published exam/learner pair, or return it.

    The exam and learner must belong to the same school. The database uniqueness
    constraint plus the transaction make concurrent first downloads idempotent.
    """
    if exam.status != "published":
        return None
    if exam.school_id != student.school_id:
        raise ValueError("Report exam and learner must belong to the same school.")
    content = bytes(pdf)
    pdf_digest = hashlib.sha256(content).hexdigest()
    source_digest = source_digest or pdf_digest
    token = sign(report_no, source_digest)
    defaults = {
        "school_id": exam.school_id,
        "report_no": report_no,
        "result_mode": result_mode,
        "pdf": content,
        "sha256": pdf_digest,
        "source_digest": source_digest,
        "verification_token": token,
        "renderer_version": 1,
    }
    existing = find_published_report(exam.school_id, exam.pk, student.pk)
    if existing:
        return existing
    try:
        with transaction.atomic():
            return PublishedReportArtifact.objects.create(
                exam=exam, student=student, **defaults)
    except IntegrityError:
        # Another authorized request created the immutable artifact first.
        existing = find_published_report(exam.school_id, exam.pk, student.pk)
        if existing is None:
            raise
        return existing


def response_for_published_report(request, artifact):
    content = bytes(artifact.pdf)
    disposition = "attachment" if request.query_params.get("download") == "1" else "inline"
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", artifact.report_no)[:80] or "report"
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'{disposition}; filename="{filename}.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Report-Reference"] = artifact.report_no
    response["X-Report-SHA256"] = artifact.sha256
    response["X-Report-Issued-At"] = artifact.issued_at.isoformat()
    response["X-Report-Archived"] = "true"
    return response
