from decimal import Decimal

from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Performance, Student, Term
from .permissions import get_user_school_id


def _avg(values):
    return round(sum(values) / len(values), 2) if values else None


@api_view(["GET"])
def report_card(request, student_id, term_id):
    students = Student.objects.all()
    if not request.user.is_superuser:
        school_id = get_user_school_id(request.user)
        if school_id is None:
            return Response({"detail": "School access not assigned."}, status=403)
        students = students.filter(school_id=school_id)
    student = students.filter(pk=student_id).first()
    if student is None:
        return Response({"detail": "Not found."}, status=404)

    term = Term.objects.select_related("academic_year").filter(
        pk=term_id, academic_year__school_id=student.school_id
    ).first()
    if term is None:
        return Response({"detail": "Not found."}, status=404)

    marks = Performance.objects.filter(student=student, term=term)
    final = marks.filter(status__in=["approved", "locked"]).select_related("subject")
    pending = marks.count() - final.count()

    by_subject = {}
    for p in final.order_by("subject__name", "assessment_type"):
        by_subject.setdefault(p.subject.name, []).append(
            (p.assessment_type, Decimal(p.marks))
        )

    subjects = []
    for name, items in by_subject.items():
        subjects.append({
            "subject": name,
            "assessments": [{"type": t, "marks": str(m)} for t, m in items],
            "average": str(_avg([m for _, m in items])),
        })
    overall = _avg([Decimal(s["average"]) for s in subjects])

    return Response({
        "student": {
            "id": student.id,
            "name": f"{student.first_name} {student.last_name}",
            "admission_number": student.admission_number,
        },
        "academic_year": term.academic_year.name,
        "term": term.name,
        "subjects": subjects,
        "overall_average": str(overall) if overall is not None else None,
        "pending_marks": pending,
    })
