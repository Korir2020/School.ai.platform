from decimal import Decimal

from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Enrollment, Exam, ExamResult, GuardianProfile, Performance, SchoolAdminProfile, Student, Term
from .permissions import get_user_school_id, restrict_for_teacher
from .subject_registration_rules import registered_marks


def _avg(values):
    return round(sum(values) / len(values), 2) if values else None


def _did_not_sit(student, term):
    """Published exams for the student's class level with no result."""
    levels = Enrollment.objects.filter(
        student=student, academic_year_id=term.academic_year_id
    ).values_list("class_level_id", flat=True)
    exams = Exam.objects.filter(
        term=term, status="published", class_level_id__in=list(levels)
    ).filter(term__academic_year__subject_registrations__student=student).distinct()
    exams = exams.exclude(results__student=student).order_by("published_at", "id")
    out = []
    for exam in exams:
        finalized = registered_marks(Performance.objects.filter(
            student=student, term=term, assessment_type=exam.assessment_type,
            status__in=["approved", "locked"],
        ), term.academic_year)
        if finalized.exists():
            # Disposition-only results (for example, all papers not assessed)
            # are visible in the subject rows and are not a no-show.
            continue
        out.append({"exam": exam.name, "assessment_type": exam.assessment_type,
                    "note": "Did not sit this exam"})
    return out


@api_view(["GET"])
def report_card(request, student_id, term_id):
    students = Student.objects.all()
    if not request.user.is_superuser:
        school_id = get_user_school_id(request.user)
        guardian = GuardianProfile.objects.filter(user=request.user).first()
        if guardian:
            students = students.filter(
                guardians__guardian=guardian, school_id=guardian.school_id,
            ).distinct()
        elif school_id is None:
            return Response({"detail": "School access not assigned."}, status=403)
        else:
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

    primary_class_ids = Enrollment.objects.filter(
        student=student, academic_year=term.academic_year, is_active=True,
    ).values_list("class_level_id", flat=True)
    primary_exam = Exam.objects.filter(
        school_id=student.school_id, term=term, status="published",
        framework_key="cbe_primary", class_level_id__in=primary_class_ids,
    ).exists()
    if primary_exam:
        return Response({
            "error": "cbc_primary_report_module_required",
            "detail": "CBC Primary report cards must be generated from Report Cards → select the published examination. That report applies this school's configured paper weights, grading rules, and approved achievement descriptors.",
        }, status=409)

    marks = registered_marks(Performance.objects.filter(student=student, term=term), term.academic_year)
    final = marks.filter(status__in=["approved", "locked"]).select_related("subject")
    pending = marks.exclude(status__in=["approved", "locked"]).count() + final.filter(
        mark_status="pending",
    ).count()

    by_subject = {}
    for p in final.order_by("subject__name", "assessment_type"):
        by_subject.setdefault(p.subject.name, []).append({
            "type": p.assessment_type,
            "marks": str(p.marks) if p.mark_status == "scored" else None,
            "status": p.mark_status,
            "_score": Decimal(p.marks) if p.mark_status == "scored" else None,
        })

    subjects = []
    for name, items in by_subject.items():
        scores = [item["_score"] for item in items if item["_score"] is not None]
        subjects.append({
            "subject": name,
            "assessments": [
                {key: value for key, value in item.items() if not key.startswith("_")}
                for item in items
            ],
            "average": str(_avg(scores)) if scores else None,
        })
    overall = _avg([Decimal(s["average"]) for s in subjects if s["average"] is not None])

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
        "mark_status_counts": {
            value: final.filter(mark_status=value).count()
            for value, _ in Performance.MARK_STATUS_CHOICES
        },
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
