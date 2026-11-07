from django.db.models import Avg, Count, Sum
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import AttendanceRecord, Enrollment, FeePayment, Performance, Student, StudentFee, StudentGuardian, Term
from .views import _scope
from .permissions import restrict_for_teacher
from .subject_registration_rules import registered_marks


def _student(request, pk):
    school_id, error = _scope(request)
    if error: return None, error
    qs = restrict_for_teacher(request.user, Student.objects.all())
    if school_id is not None: qs = qs.filter(school_id=school_id)
    student = qs.filter(pk=pk).first()
    return student, Response({"detail": "Not found."}, status=404) if not student else None


@api_view(["GET"])
def student_center(request, pk):
    student, error = _student(request, pk)
    if error: return error
    enrollments = Enrollment.objects.filter(student=student).select_related("academic_year", "class_level", "stream").order_by("-academic_year__start_date")
    terms = Term.objects.filter(academic_year__school_id=student.school_id).select_related("academic_year").order_by("-start_date")
    history = []
    for term in terms:
        outcomes = registered_marks(
            Performance.objects.filter(student=student, term=term,
                                       status__in=["approved", "locked"]),
            term.academic_year,
        )
        marks = outcomes.filter(mark_status="scored")
        agg = marks.aggregate(average=Avg("marks"))
        if outcomes.exists():
            subject_rows = list(marks.values("subject__name").annotate(
                average=Avg("marks"), entries=Count("id"),
            ).order_by("subject__name"))
            dispositions = {}
            for row in outcomes.values("subject__name", "mark_status").annotate(count=Count("id")):
                dispositions.setdefault(row["subject__name"], {})[row["mark_status"]] = row["count"]
            for row in subject_rows:
                row["mark_status_counts"] = dispositions.get(row["subject__name"], {})
            history.append({
                "term_id": term.id, "term": term.name,
                "academic_year": term.academic_year.name,
                "average": round(float(agg["average"]), 2) if agg["average"] is not None else None,
                "entries": marks.count(), "subjects": subject_rows,
                "mark_status_counts": {
                    status: outcomes.filter(mark_status=status).count()
                    for status, _ in Performance.MARK_STATUS_CHOICES
                },
            })
    fees = StudentFee.objects.filter(student=student).select_related("fee_structure").order_by("-id")
    payments = FeePayment.objects.filter(student_fee__student=student).select_related("student_fee__fee_structure").order_by("-paid_at")
    totals = fees.aggregate(due=Sum("amount_due"), paid=Sum("amount_paid"))
    guardians = StudentGuardian.objects.filter(student=student).select_related("guardian__user")
    attendance = AttendanceRecord.objects.filter(student=student)
    counts = {status: attendance.filter(status=status).count() for status, _ in AttendanceRecord.STATUSES}
    return Response({"student": {"id": student.id, "name": str(student), "first_name": student.first_name, "last_name": student.last_name, "admission_number": student.admission_number, "date_of_birth": student.date_of_birth}, "enrollments": [{"academic_year": e.academic_year.name, "class": e.class_level.name, "stream": e.stream.name if e.stream else "Unassigned", "active": e.is_active} for e in enrollments], "history": history, "attendance": {"counts": counts, "total": attendance.count(), "records": [{"date": x.date, "status": x.status, "notes": x.notes} for x in attendance[:100]]}, "fees": [{"id": f.id, "fee": f.fee_structure.name, "due": str(f.amount_due), "paid": str(f.amount_paid), "balance": str(f.balance), "status": f.status} for f in fees], "payments": [{"id": p.id, "receipt_number": f"RCPT-{student.school.code}-{p.id:06d}", "amount": str(p.amount), "method": p.get_method_display(), "reference": p.reference, "paid_at": p.paid_at} for p in payments], "fee_totals": {"due": str(totals["due"] or 0), "paid": str(totals["paid"] or 0), "balance": str((totals["due"] or 0) - (totals["paid"] or 0))}, "guardians": [{"name": str(g.guardian.user.get_full_name() or g.guardian.user.username), "relationship": g.relationship, "phone": g.guardian.phone} for g in guardians]})
