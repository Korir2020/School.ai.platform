from decimal import Decimal
from rest_framework.decorators import api_view
from rest_framework.response import Response
from schools.models import ExamResult, Student
from .progress import analyse
from .results import _admin_scope


@api_view(["GET"])
def student_progress(request, student_id):
    school_id, error = _admin_scope(request)
    if error:
        return error
    students = Student.objects.all()
    if school_id is not None:
        students = students.filter(school_id=school_id)
    student = students.filter(pk=student_id).first()
    if student is None:
        return Response({"detail": "Not found."}, status=404)
    results = ExamResult.objects.filter(
        student=student, exam__status="published"
    ).select_related("exam").order_by("exam__published_at", "exam_id")
    points = [
        (r.exam.name, r.overall_average,
         {k: Decimal(v) for k, v in r.subject_scores.items()})
        for r in results
    ]
    return Response({"student": f"{student.first_name} {student.last_name}",
                     **analyse(points),
                     "note": "For staff review only. Nothing here changes any record."})
