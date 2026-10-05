from decimal import Decimal

from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Enrollment, Exam, ExamResult, Performance, SchoolAdminProfile, Student, Term
from .permissions import get_user_school_id, restrict_for_teacher


def _avg(values):
    return round(sum(values) / len(values), 2) if values else None


def _did_not_sit(student, term):
    """Published exams for the student's class level with no result."""
    levels = Enrollment.objects.filter(
        student=student, academic_year_id=term.academic_year_id
    ).values_list("class_level_id", flat=True)
    exams = Exam.objects.filter(
        term=term, status="published", class_level_id__in=list(levels)
    ).exclude(results__student=student).order_by("published_at", "id")
    return [
        {"exam": e.name, "assessment_type": e.assessment_type,
         "note": "Did not sit this exam"}
        for e in exams
    ]


@api_view(["GET"])
def report_card(request, student_id, term_id):
    students = Student.objects.all()
    if not request.user.is_superuser:
        school_id = get_user_school_id(request.user)
        if school_id is None:
            return Response({"detail": "School access not assigned."}, status=403)
        students = students.filter(school_id=school_id)
    students = restrict_for_teacher(request.user, students)
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

    data = {
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
        "did_not_sit": _did_not_sit(student, term),
    }

    is_admin = request.user.is_superuser or SchoolAdminProfile.objects.filter(
        user=request.user
    ).exists()
    if is_admin:
        results = (
            ExamResult.objects.filter(
                student=student, exam__term=term, exam__status="published"
            )
            .select_related("exam")
            .order_by("exam__published_at")
        )
        data["published_results"] = [
            {
                "exam": r.exam.name,
                "assessment_type": r.exam.assessment_type,
                "overall_average": str(r.overall_average),
                "stream_rank": r.stream_rank,
                "class_rank": r.class_rank,
            }
            for r in results
        ]
    return Response(data)
