import csv
import io

from django.db.models import Avg, Count, Max, Min, Sum
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from schools.models import Enrollment, Performance, SchoolAdminProfile, StaffProfile, StudentFee, Stream, Term
from .permissions import get_user_school_id
from api.fee_permissions import get_fee_access_school_id
from .subject_registration_rules import registered_marks


def _term_for(request, term_id):
    qs = Term.objects.select_related("academic_year")
    if not request.user.is_superuser:
        qs = qs.filter(academic_year__school_id=get_user_school_id(request.user))
    return qs.filter(id=term_id).first()


def _final_rows(term):
    return registered_marks(
        Performance.objects.filter(term=term, status__in=["approved", "locked"]),
        term.academic_year,
    )


def _final_marks(term):
    return _final_rows(term).filter(mark_status="scored")


def _trend(school_id, academic_year):
    terms = Term.objects.filter(academic_year__school_id=school_id, academic_year=academic_year).order_by("start_date")
    output = []
    for item in terms:
        marks = _final_marks(item).filter(student__school_id=school_id)
        avg = marks.aggregate(x=Avg("marks"))["x"]
        output.append({"term_id": item.id, "term": item.name, "average": round(float(avg), 2) if avg is not None else None, "entries": marks.count(), "students": marks.values("student_id").distinct().count()})
    return output


def _distribution(marks):
    buckets = [(0, 39, "0–39"), (40, 49, "40–49"), (50, 59, "50–59"), (60, 69, "60–69"), (70, 79, "70–79"), (80, 100, "80–100")]
    return [{"label": label, "count": marks.filter(marks__gte=lo, marks__lte=hi).count()} for lo, hi, label in buckets]


def _avg_map(qs, field):
    return list(qs.values(field).annotate(average=Avg("marks"), entries=Count("id"), highest=Max("marks"), lowest=Min("marks")).order_by(field))


@api_view(["GET"])
def advanced_report(request, term_id):
    is_admin = SchoolAdminProfile.objects.filter(user=request.user).exists()
    is_bursar = StaffProfile.objects.filter(user=request.user, role="bursar").exists()
    bursar_only = is_bursar and not is_admin and not request.user.is_superuser
    if not request.user.is_superuser and not is_admin and not is_bursar:
        return Response({"detail": "Admins only."}, status=403)
    if bursar_only:
        try:
            fee_school_id = get_fee_access_school_id(request.user)
        except PermissionDenied as exc:
            return Response({"detail": str(exc.detail)}, status=403)
        term = Term.objects.select_related("academic_year").filter(
            id=term_id, academic_year__school_id=fee_school_id).first()
    else:
        term = _term_for(request, term_id)
    if not term:
        return Response({"detail": "Not found."}, status=404)
    school_id = term.academic_year.school_id
    if bursar_only:
        finance = StudentFee.objects.filter(student__school_id=school_id).aggregate(
            due=Sum("amount_due"), paid=Sum("amount_paid"))
        due, paid = finance["due"] or 0, finance["paid"] or 0
        return Response({
            "term": term.name, "term_id": term.id,
            "academic_year": term.academic_year.name,
            "finance": {"billed": str(due), "collected": str(paid),
                        "outstanding": str(max(due - paid, 0)),
                        "collection_rate": round(float(paid / due * 100), 1) if due else None},
        })
    outcomes = _final_rows(term)
    marks = outcomes.filter(mark_status="scored")
    enrollment = Enrollment.objects.filter(academic_year=term.academic_year, is_active=True, student__school_id=school_id).select_related("class_level", "stream")
    class_map = {x.student_id: x.class_level.name for x in enrollment}
    stream_map = {x.student_id: x.stream.name if x.stream else "Unassigned" for x in enrollment}
    class_filter = request.GET.get("class_level_id")
    stream_filter = request.GET.get("stream_id")
    subject_filter = request.GET.get("subject_id")
    if class_filter:
        ids = [x.student_id for x in enrollment if str(x.class_level_id) == str(class_filter)]
        marks, outcomes = marks.filter(student_id__in=ids), outcomes.filter(student_id__in=ids)
    if stream_filter:
        ids = [x.student_id for x in enrollment if str(x.stream_id) == str(stream_filter)]
        marks, outcomes = marks.filter(student_id__in=ids), outcomes.filter(student_id__in=ids)
    if subject_filter:
        marks, outcomes = marks.filter(subject_id=subject_filter), outcomes.filter(subject_id=subject_filter)
    student_names = dict(marks.values_list("student_id", "student__first_name"))
    last_names = dict(marks.values_list("student_id", "student__last_name"))
    rows = []
    student_averages = marks.values("student_id").annotate(average=Avg("marks"), entries=Count("id"))
    for row in student_averages:
        sid = row["student_id"]
        rows.append({"student_id": sid, "student_name": f"{student_names.get(sid, '')} {last_names.get(sid, '')}".strip(), "average": round(float(row["average"]), 2), "entries": row["entries"], "class": class_map.get(sid, ""), "stream": stream_map.get(sid, "")})
    class_rows = {}
    stream_rows = {}
    for row in rows:
        class_rows.setdefault(row["class"], []).append(row["average"])
        stream_rows.setdefault(row["stream"], []).append(row["average"])
    def grouped(source):
        return [{"name": name, "average": round(sum(values) / len(values), 2), "students": len(values)} for name, values in sorted(source.items()) if name]
    prior = Term.objects.filter(academic_year=term.academic_year, end_date__lt=term.start_date).order_by("-end_date").first()
    prior_map = {}
    if prior:
        prior_map = {x["student_id"]: float(x["average"]) for x in _final_marks(prior).values("student_id").annotate(average=Avg("marks"))}
    improvement = sorted([{"student_id": row["student_id"], "student_name": row["student_name"], "current": row["average"], "previous": prior_map[row["student_id"]], "change": round(row["average"] - prior_map[row["student_id"]], 2)} for row in rows if row["student_id"] in prior_map], key=lambda x: x["change"], reverse=True)
    at_risk = [row for row in rows if row["average"] < 50 or row["entries"] < 2]
    subjects = [{"subject": x["subject__name"], "average": round(float(x["average"]), 2), "entries": x["entries"], "highest": str(x["highest"]), "lowest": str(x["lowest"])} for x in _avg_map(marks, "subject__name")]
    finalized = marks.count()
    passed = marks.filter(marks__gte=50).count()
    try:
        get_fee_access_school_id(request.user, school_id=school_id)
    except PermissionDenied:
        fee_finance = None
    else:
        finance = StudentFee.objects.filter(student__school_id=school_id).aggregate(due=Sum("amount_due"), paid=Sum("amount_paid"))
        due, paid = finance["due"] or 0, finance["paid"] or 0
        fee_finance = {"billed": str(due), "collected": str(paid),
                       "outstanding": str(max(due - paid, 0)),
                       "collection_rate": round(float(paid / due * 100), 1) if due else None}
    weakest = sorted(subjects, key=lambda x: x["average"])[:3]
    insights = []
    if finalized: insights.append({"kind": "observation", "title": f"Pass rate is {round(passed / finalized * 100, 1)}%", "evidence": f"{passed} of {finalized} finalized marks are 50% or higher.", "next_step": "Review the subject and class breakdowns below."})
    for item in weakest: insights.append({"kind": "observation", "title": f"Subject weakness: {item['subject']}", "evidence": f"Average {item['average']}% across {item['entries']} finalized entries.", "next_step": "Review topic-level teaching support and reassessment needs."})
    if at_risk: insights.append({"kind": "rule_alert", "title": f"{len(at_risk)} students require attention", "evidence": "Average below 50% or fewer than two finalized entries.", "next_step": "Open the student list and record a supportive intervention."})
    mark_status_counts = {
        value: outcomes.filter(mark_status=value).count()
        for value in ("scored", "absent", "exempted", "not_assessed", "pending")
    }
    payload = {"term": term.name, "term_id": term.id, "academic_year": term.academic_year.name, "classes": grouped(class_rows), "streams": grouped(stream_rows), "subjects": subjects, "improvement": improvement[:50], "at_risk": at_risk, "finalized_entries": finalized, "mark_status_counts": mark_status_counts, "students_with_finalized_marks": len(rows), "previous_term": {"id": prior.id, "name": prior.name} if prior else None, "trend": _trend(school_id, term.academic_year), "distribution": _distribution(marks), "pass_rate": round(passed / finalized * 100, 1) if finalized else None, "insights": insights}
    if fee_finance is not None:
        payload["finance"] = fee_finance
    export = request.query_params.get("format") or request.query_params.get("export")
    if not export:
        raw_query = request.META.get("QUERY_STRING", "")
        if "format=csv" in raw_query or "export=csv" in raw_query: export = "csv"
        if "format=pdf" in raw_query or "export=pdf" in raw_query: export = "pdf"
    if export == "csv":
        out = io.StringIO(); writer = csv.writer(out); writer.writerow(["Student", "Class", "Stream", "Average", "Finalized entries"])
        writer.writerows([[x["student_name"], x["class"], x["stream"], x["average"], x["entries"]] for x in rows])
        writer.writerow([]); writer.writerow(["Finalized mark dispositions"]); writer.writerow(["Status", "Count"])
        writer.writerows([[status, count] for status, count in mark_status_counts.items()])
        response = HttpResponse(out.getvalue(), content_type="text/csv"); response["Content-Disposition"] = 'attachment; filename="academic-report.csv"'; return response
    if export == "pdf":
        buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm); styles = getSampleStyleSheet(); story = [Paragraph(f"Academic Performance Report · {term.name} {term.academic_year.name}", styles["Title"]), Spacer(1, 6 * mm)]
        table = [["Student", "Class", "Stream", "Average", "Entries"]] + [[x["student_name"], x["class"], x["stream"], f'{x["average"]}%', x["entries"]] for x in rows]
        t = Table(table, repeatRows=1); t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F2747")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CBD5E1")), ("FONTSIZE", (0, 0), (-1, -1), 8), ("PADDING", (0, 0), (-1, -1), 5)])); story.append(t)
        story.append(Spacer(1, 4 * mm)); story.append(Paragraph("Finalized mark dispositions", styles["Heading2"]))
        status_table = Table([["Status", "Count"]] + [[key.replace("_", " ").title(), value] for key, value in mark_status_counts.items()])
        status_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F2747")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CBD5E1")), ("FONTSIZE", (0, 0), (-1, -1), 8), ("PADDING", (0, 0), (-1, -1), 5)])); story.append(status_table)
        doc.build(story); response = HttpResponse(buf.getvalue(), content_type="application/pdf"); response["Content-Disposition"] = 'attachment; filename="academic-report.pdf"'; return response
    return Response(payload)
