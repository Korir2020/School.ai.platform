from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Exam, ExamResult, SchoolAdminProfile, Student
from .permissions import get_user_school_id


def _admin_scope(request):
    """Return (school_id, error). school_id None + no error = superuser."""
    if request.user.is_superuser:
        return None, None
    if not SchoolAdminProfile.objects.filter(user=request.user).exists():
        return None, Response({"detail": "Admins only."}, status=403)
    return get_user_school_id(request.user), None


@api_view(["GET"])
def exam_results(request, pk):
    school_id, error = _admin_scope(request)
    if error:
        return error
    exams = Exam.objects.all()
    if school_id is not None:
        exams = exams.filter(school_id=school_id)
    exam = exams.filter(pk=pk).first()
    if exam is None:
        return Response({"detail": "Not found."}, status=404)
    if exam.status != "published":
        return Response({"detail": "Exam is not published yet."}, status=409)
    results = (
        ExamResult.objects.filter(exam=exam)
        .select_related("student")
        .order_by("class_rank", "student__admission_number")
    )
    return Response({
        "exam": exam.name,
        "results": [
            {
                "student_id": r.student_id,
                "name": f"{r.student.first_name} {r.student.last_name}",
                "admission_number": r.student.admission_number,
                "overall_average": str(r.overall_average),
                "stream_rank": r.stream_rank,
                "class_rank": r.class_rank,
                "subject_scores": r.subject_scores,
            }
            for r in results
        ],
    })


@api_view(["GET"])
def student_exam_history(request, student_id):
    school_id, error = _admin_scope(request)
    if error:
        return error
    students = Student.objects.all()
    if school_id is not None:
        students = students.filter(school_id=school_id)
    student = students.filter(pk=student_id).first()
    if student is None:
        return Response({"detail": "Not found."}, status=404)
    results = (
        ExamResult.objects.filter(student=student)
        .select_related("exam__term")
        .order_by("exam__published_at")
    )
    return Response({
        "student": f"{student.first_name} {student.last_name}",
        "history": [
            {
                "exam": r.exam.name,
                "term": r.exam.term.name,
                "assessment_type": r.exam.assessment_type,
                "published_at": r.exam.published_at,
                "overall_average": str(r.overall_average),
                "stream_rank": r.stream_rank,
                "class_rank": r.class_rank,
            }
            for r in results
        ],
    })
