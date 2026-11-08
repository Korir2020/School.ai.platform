import io
import zipfile
from collections import defaultdict
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, Exam, ExamResult, FeePayment, Performance, SchoolAdminProfile,
    StaffProfile, Student, StudentFee, Term,
)
from .subject_registration_rules import registered_marks
from .permissions import get_user_school_id
from .pagination import paginated_mapped_response
from .background_jobs import (
    ASYNC_DOCUMENT_THRESHOLD, MAX_DOCUMENT_BATCH, _safe_name,
    enqueue_document_job,
)
from .fee_permissions import get_fee_access_school_id

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.platypus import Image as ReportImage
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover - deployment dependency check
    colors = None


def _school_id(request, roles=("admin", "bursar")):
    if request.user.is_superuser:
        return None, None
    admin = SchoolAdminProfile.objects.filter(user=request.user).first()
    if admin and "admin" in roles:
        return admin.school_id, None
    bursar = StaffProfile.objects.filter(user=request.user, role="bursar").first()
    if bursar and "bursar" in roles:
        return bursar.school_id, None
    return None, Response({"detail": "You do not have permission to generate documents."}, status=403)


def _school_filter(qs, school_id):
    return qs if school_id is None else qs.filter(school_id=school_id)


def _students(request, school_id):
    qs = Student.objects.all()
    if school_id is not None:
        qs = qs.filter(school_id=school_id)
    ids = request.data.get("student_ids") or request.GET.get("student_ids")
    if ids:
        if isinstance(ids, str):
            ids = [x for x in ids.split(",") if x.strip()]
        qs = qs.filter(id__in=ids)
    class_level = request.data.get("class_level_id") or request.GET.get("class_level_id")
    stream = request.data.get("stream_id") or request.GET.get("stream_id")
    if class_level or stream:
        enrollments = Enrollment.objects.all()
        if school_id is not None:
            enrollments = enrollments.filter(academic_year__school_id=school_id)
        if class_level:
            enrollments = enrollments.filter(class_level_id=class_level)
        if stream:
            enrollments = enrollments.filter(stream_id=stream)
        qs = qs.filter(id__in=enrollments.values("student_id"))
    return qs.order_by("last_name", "first_name", "admission_number")


def _term(request, school_id):
    term_id = request.data.get("term_id") or request.GET.get("term_id")
    qs = Term.objects.select_related("academic_year")
    if school_id is not None:
        qs = qs.filter(academic_year__school_id=school_id)
    return qs.filter(id=term_id).first() if term_id else qs.filter(is_active=True).order_by("-start_date").first()


def _eligible_report_students(request, school_id, term):
    students = _students(request, school_id)
    if not term:
        return students.none()
    # A student is eligible when at least one approved/locked mark exists for the term.
    eligible_ids = registered_marks(
        Performance.objects.filter(term=term, status__in=["approved", "locked"],
                                   student__in=students), term.academic_year
    ).values_list("student_id", flat=True).distinct()
    return students.filter(id__in=eligible_ids)


def _parse_id_list(raw, label):
    if raw in (None, ""):
        return None, None
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",") if item.strip()]
    if not isinstance(raw, list):
        return None, f"{label} must be a list of ids."
    if len(raw) > MAX_DOCUMENT_BATCH:
        return None, f"Select at most {MAX_DOCUMENT_BATCH:,} records per export."
    values, seen = [], set()
    for item in raw:
        if isinstance(item, bool) or not (
            isinstance(item, int)
            or isinstance(item, str) and item.isdigit()
        ):
            return None, f"{label} contains an invalid id."
        value = int(item)
        if value <= 0 or value in seen:
            return None, f"{label} contains a duplicate or invalid id."
        values.append(value)
        seen.add(value)
    return values, None


def _job_response(job):
    return Response({
        "job_id": str(job.pk), "status": job.status,
        "total": job.total, "progress": job.progress,
        "status_url": f"/api/jobs/{job.pk}/",
        "detail": "Your export has been queued. You can check its progress here.",
    }, status=202)


def _published_result(student, term):
    return ExamResult.objects.filter(student=student, exam__term=term,
                                     exam__status="published").select_related("exam").order_by("-exam__published_at", "-id").first()


def _class_name(student, term):
    enrollment = Enrollment.objects.filter(student=student, academic_year=term.academic_year,
                                           is_active=True).select_related("class_level", "stream").first()
    if not enrollment:
        return "", ""
    return enrollment.class_level.name, enrollment.stream.name if enrollment.stream else ""


_UNSET = object()


def _report_payload(student, term, marks=None, result=_UNSET, enrollment=_UNSET):
    if marks is None:
        marks = registered_marks(
            Performance.objects.filter(student=student, term=term,
                                       status__in=["approved", "locked"]), term.academic_year
        ).select_related("subject").order_by("subject__name", "assessment_type", "paper_number")
    by_subject = {}
    status_counts = {"scored": 0, "absent": 0, "exempted": 0,
                     "not_assessed": 0, "pending": 0}
    for mark in marks:
        status_counts[mark.mark_status] = status_counts.get(mark.mark_status, 0) + 1
        item = by_subject.setdefault(mark.subject.name, {"marks": [], "dispositions": []})
        if mark.mark_status == "scored":
            item["marks"].append(mark.marks)
        else:
            item["dispositions"].append(
                f"{mark.assessment_type} Paper {mark.paper_number}: {mark.mark_status.replace('_', ' ')}"
            )
    subjects = []
    for name, item in by_subject.items():
        values = item["marks"]
        total = sum(values, Decimal("0"))
        subjects.append({"subject": name, "marks": [str(x) for x in values],
                         "dispositions": item["dispositions"], "total": str(total),
                         "average": str((total / len(values)).quantize(Decimal("0.01"))) if values else None})
    if result is _UNSET:
        result = _published_result(student, term)
    if enrollment is _UNSET:
        class_name, stream = _class_name(student, term)
    else:
        class_name = enrollment.class_level.name if enrollment else ""
        stream = enrollment.stream.name if enrollment and enrollment.stream else ""
    numeric_averages = [Decimal(x["average"]) for x in subjects if x["average"] is not None]
    return {"student": str(student), "admission_number": student.admission_number,
            "class": class_name, "stream": stream, "academic_year": term.academic_year.name,
            "term": term.name, "subjects": subjects,
            "mark_status_counts": status_counts,
            "total": str(sum((Decimal(x["total"]) for x in subjects), Decimal("0"))),
            "average": str((sum(numeric_averages, Decimal("0")) / len(numeric_averages)).quantize(Decimal("0.01"))) if numeric_averages else None,
            "class_position": result.class_rank if result else None,
            "stream_position": result.stream_rank if result else None,
            "exam_average": str(result.overall_average) if result else None,
            "eligible": bool(subjects)}


def _report_payloads(students, term):
    """Build report data for a cohort using three shared database queries."""
    students = list(students)
    ids = [student.id for student in students]
    if not ids:
        return {}
    marks_by_student = defaultdict(list)
    marks = registered_marks(
        Performance.objects.filter(
            student_id__in=ids, term=term, status__in=["approved", "locked"],
        ), term.academic_year,
    ).select_related("subject").order_by(
        "subject__name", "assessment_type", "paper_number",
    )
    for mark in marks:
        marks_by_student[mark.student_id].append(mark)

    results_by_student = {}
    results = ExamResult.objects.filter(
        student_id__in=ids, exam__term=term, exam__status="published",
    ).select_related("exam").order_by("-exam__published_at", "-id")
    for result in results:
        results_by_student.setdefault(result.student_id, result)

    enrollments_by_student = {}
    enrollments = Enrollment.objects.filter(
        student_id__in=ids, academic_year=term.academic_year, is_active=True,
    ).select_related("class_level", "stream").order_by("id")
    for enrollment in enrollments:
        enrollments_by_student.setdefault(enrollment.student_id, enrollment)

    return {
        student.id: _report_payload(
            student, term, marks=marks_by_student.get(student.id, []),
            result=results_by_student.get(student.id),
            enrollment=enrollments_by_student.get(student.id),
        ) for student in students
    }


def _styles():
    base = getSampleStyleSheet()
    return base["BodyText"], ParagraphStyle("Small", parent=base["BodyText"], fontSize=8, leading=10), ParagraphStyle("Title2", parent=base["Title"], fontSize=16, leading=20, textColor=colors.HexColor("#0F2747"))


def _header(story, school, title, subtitle):
    body, small, title_style = _styles()
    if getattr(school, "logo", None) and school.logo.name:
        try:
            logo = ReportImage(school.logo.path, width=24 * mm, height=24 * mm, kind="proportional")
            story.append(logo)
        except (OSError, ValueError):
            pass
    story.extend([Paragraph(school.name, title_style), Paragraph(f"{school.location or ''} {school.phone or ''} {school.email or ''}", small), Spacer(1, 5 * mm), Paragraph(title, ParagraphStyle("DocTitle", parent=title_style, fontSize=13)), Paragraph(subtitle, small), Spacer(1, 5 * mm)])


def _report_pdf(student, term, school, payload=None):
    buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=13 * mm, bottomMargin=13 * mm)
    story = []; payload = payload or _report_payload(student, term); body, small, _ = _styles()
    _header(story, school, "STUDENT REPORT CARD", f"{payload['academic_year']} · {payload['term']}")
    identity = [["Student", payload["student"], "Admission", payload["admission_number"]], ["Class", payload["class"] or "Not recorded", "Stream", payload["stream"] or "Not recorded"]]
    t = Table(identity, colWidths=[25 * mm, 65 * mm, 25 * mm, 65 * mm]); t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CBD5E1")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1F5F9")), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("PADDING", (0, 0), (-1, -1), 6)])); story.append(t); story.append(Spacer(1, 6 * mm))
    rows = [["Subject", "Marks", "Disposition", "Total", "Average"]] + [[x["subject"], ", ".join(x["marks"]), ", ".join(x["dispositions"]) or "—", x["total"], x["average"] or "—"] for x in payload["subjects"]]
    table = Table(rows, colWidths=[44 * mm, 32 * mm, 56 * mm, 24 * mm, 24 * mm]); table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F2747")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CBD5E1")), ("FONTSIZE", (0, 0), (-1, -1), 8), ("PADDING", (0, 0), (-1, -1), 5)])); story.append(table); story.append(Spacer(1, 6 * mm))
    summary = [["Overall average", payload["average"] or "Not available"], ["Class position", str(payload["class_position"] or "Not available")], ["Stream position", str(payload["stream_position"] or "Not available")]]
    st = Table(summary, colWidths=[55 * mm, 45 * mm]); st.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E6F4F4")), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CBD5E1")), ("PADDING", (0, 0), (-1, -1), 6)])); story.append(st); story.append(Spacer(1, 10 * mm)); story.append(Paragraph("Only approved or locked marks and published examination ranks are included. Grading labels and comments are omitted when not configured in the school system.", small)); doc.build(story); return buf.getvalue()


def _receipt_number(payment):
    return f"RCPT-{payment.student_fee.student.school.code}-{payment.id:06d}"


def _receipt_pdf(payment, school):
    buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm)
    story = []; body, small, _ = _styles(); _header(story, school, "OFFICIAL FEE RECEIPT", _receipt_number(payment))
    invoice = payment.student_fee
    rows = [["Receipt number", _receipt_number(payment)], ["Student", str(invoice.student)], ["Admission number", invoice.student.admission_number], ["Fee", invoice.fee_structure.name], ["Amount paid", f"KES {payment.amount:,.2f}"], ["Payment date", payment.paid_at.strftime("%d %b %Y %H:%M")], ["Method", payment.get_method_display()], ["Transaction reference", payment.reference or "Not provided"]]
    table = Table(rows, colWidths=[55 * mm, 105 * mm]); table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CBD5E1")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("PADDING", (0, 0), (-1, -1), 8), ("FONTSIZE", (0, 0), (-1, -1), 10)])); story.append(table); story.append(Spacer(1, 12 * mm)); story.append(Paragraph("This receipt represents a payment already recorded in the school system. Keep it for your records.", small)); doc.build(story); return buf.getvalue()


def _combined(pdfs):
    writer = PdfWriter()
    for raw in pdfs:
        reader = PdfReader(io.BytesIO(raw))
        for page in reader.pages: writer.add_page(page)
    out = io.BytesIO(); writer.write(out); return out.getvalue()


def _zip_files(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, raw in files: z.writestr(name, raw)
    return out.getvalue()


def _file_response(raw, name, content_type):
    response = HttpResponse(raw, content_type=content_type); response["Content-Disposition"] = f'attachment; filename="{name}"'; return response


@api_view(["GET", "POST"])
def bulk_report_cards(request):
    school_id, error = _school_id(request, ("admin",))
    if error: return error
    if request.user.is_superuser and not (request.GET.get("term_id") or request.data.get("term_id")):
        return Response({"detail": "Select a term from one school."}, status=400)
    term = _term(request, school_id)
    if not term: return Response({"detail": "Select a valid term."}, status=400)
    # The term is an explicit tenant selector for platform superusers too.
    tenant_id = school_id or term.academic_year.school_id
    students = _eligible_report_students(request, tenant_id, term)
    if request.method == "GET":
        response = paginated_mapped_response(
            request,
            students.select_related("school").order_by("last_name", "first_name", "id"),
            lambda s: {"id": s.id, "name": str(s),
                       "admission_number": s.admission_number},
        )
        response.data["term"] = {
            "id": term.id, "name": term.name,
            "academic_year": term.academic_year.name,
        }
        response.data["eligible_count"] = response.data["count"]
        response.data["students"] = response.data["results"]
        return response
    fmt = request.data.get("format", "combined")
    if fmt not in {"combined", "zip", "both"}:
        return Response({"detail": "Format must be combined, zip, or both."}, status=400)
    requested_ids, id_error = _parse_id_list(
        request.data.get("student_ids"), "Student selection",
    )
    if id_error:
        return Response({"detail": id_error}, status=400)
    if requested_ids is not None:
        students = students.filter(pk__in=requested_ids)
        if students.count() != len(requested_ids):
            return Response({"detail": "One or more selected learners are not eligible in this school and term."}, status=400)
    total = students.count()
    if total == 0:
        return Response({"detail": "No eligible students selected."}, status=400)
    if total > MAX_DOCUMENT_BATCH:
        return Response({"detail": f"Select at most {MAX_DOCUMENT_BATCH:,} learners per export."}, status=400)
    school = term.academic_year.school
    if total >= ASYNC_DOCUMENT_THRESHOLD:
        ids = list(students.order_by("id").values_list("id", flat=True))
        job = enqueue_document_job(
            school=school, user=request.user, job_type="report_cards",
            payload={"term_id": term.id, "student_ids": ids, "format": fmt},
            total=len(ids),
        )
        return _job_response(job)

    students = students.select_related("school").order_by("last_name", "first_name", "id")
    files = [(f"report-card-{_safe_name(s.admission_number)}.pdf", _report_pdf(s, term, school)) for s in students]
    if fmt == "zip": return _file_response(_zip_files(files), "report-cards.zip", "application/zip")
    combined = _combined([raw for _, raw in files])
    if fmt == "both": return _file_response(_zip_files([("report-cards-combined.pdf", combined)] + files), "report-cards-both.zip", "application/zip")
    return _file_response(combined, "report-cards.pdf", "application/pdf")


@api_view(["GET", "POST"])
def fee_receipts(request):
    raw_school_id = request.data.get("school_id") if request.method == "POST" else request.GET.get("school_id")
    if raw_school_id is None:
        school_id = get_fee_access_school_id(request.user)
    elif not isinstance(raw_school_id, (int, str)) or isinstance(raw_school_id, bool) or not str(raw_school_id).isdigit():
        return Response({"detail": "school_id must be a valid school ID."}, status=400)
    else:
        school_id = get_fee_access_school_id(request.user, school_id=int(raw_school_id))
    qs = FeePayment.objects.select_related("student_fee__student__school", "student_fee__fee_structure")
    qs = qs.filter(student_fee__student__school_id=school_id)
    raw_ids = request.data.get("payment_ids") if request.method == "POST" else request.GET.get("payment_ids")
    ids, id_error = _parse_id_list(raw_ids, "Payment selection")
    if id_error:
        return Response({"detail": id_error}, status=400)
    if ids is not None:
        qs = qs.filter(id__in=ids)
        if qs.count() != len(ids):
            return Response({"detail": "You do not have permission to access fee information."}, status=403)
    if request.method == "GET":
        response = paginated_mapped_response(
            request, qs.order_by("-paid_at", "-id"),
            lambda p: {
                "id": p.id, "receipt_number": _receipt_number(p),
                "student": str(p.student_fee.student),
                "amount": str(p.amount), "paid_at": p.paid_at,
            },
        )
        response.data["payments"] = response.data["results"]
        return response
    payment_ids = list(qs.order_by("id").values_list("id", flat=True)[:MAX_DOCUMENT_BATCH + 1])
    if len(payment_ids) > MAX_DOCUMENT_BATCH:
        return Response({"detail": f"Select at most {MAX_DOCUMENT_BATCH:,} payments per export."}, status=400)
    payments = list(qs.filter(pk__in=payment_ids).order_by("id"))
    if not payments: return Response({"detail": "No recorded payments selected."}, status=400)
    fmt = request.data.get("format", "combined")
    if fmt not in {"combined", "zip", "both"}:
        return Response({"detail": "Format must be combined, zip, or both."}, status=400)
    if len(payments) >= ASYNC_DOCUMENT_THRESHOLD:
        job = enqueue_document_job(
            school=payments[0].student_fee.student.school, user=request.user,
            job_type="fee_receipts",
            payload={"payment_ids": payment_ids, "format": fmt},
            total=len(payment_ids),
        )
        return _job_response(job)
    files = [(f"receipt-{_safe_name(_receipt_number(p))}.pdf", _receipt_pdf(p, p.student_fee.student.school)) for p in payments]
    if fmt == "zip": return _file_response(_zip_files(files), "fee-receipts.zip", "application/zip")
    combined = _combined([raw for _, raw in files])
    if fmt == "both": return _file_response(_zip_files([("fee-receipts-combined.pdf", combined)] + files), "fee-receipts-both.zip", "application/zip")
    return _file_response(combined, "fee-receipts.pdf", "application/pdf")
