from collections import defaultdict
from rest_framework.decorators import api_view
from rest_framework.response import Response
from schools.models import ExamResult
from .results import _admin_scope

DROP = 10  # points lost since previous exam
LOW = 40   # latest overall average below this


def reasons_for(results):
    """One student's ExamResults, oldest first."""
    last = float(results[-1].overall_average)
    reasons = []
    if len(results) > 1:
        prev = float(results[-2].overall_average)
        if prev - last >= DROP:
            reasons.append(
                f"Fell {prev - last:.1f} points since "
                f"{results[-2].exam.name}")
    if last < LOW:
        reasons.append(f"Latest average {last:.1f} is below {LOW}")
    return reasons


@api_view(["GET"])
def early_warning(request):
    school_id, error = _admin_scope(request)
    if error:
        return error
    qs = ExamResult.objects.filter(exam__status="published")
    if school_id is not None:
        qs = qs.filter(exam__school_id=school_id)
    qs = qs.select_related("student", "exam").order_by("exam__published_at", "id")
    by_student = defaultdict(list)
    for r in qs:
        by_student[r.student].append(r)
    flagged = []
    for student, rs in by_student.items():
        reasons = reasons_for(rs)
        if reasons:
            flagged.append({
                "student_id": student.id,
                "name": f"{student.first_name} {student.last_name}",
                "admission_number": student.admission_number,
                "latest_average": str(rs[-1].overall_average),
                "reasons": reasons,
            })
    flagged.sort(key=lambda f: float(f["latest_average"]))
    return Response({"count": len(flagged), "results": flagged})
