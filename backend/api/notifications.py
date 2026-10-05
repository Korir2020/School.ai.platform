from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Exam, MarkAuditLog, Performance, SchoolAdminProfile

DAYS = 30


@api_view(["GET"])
def notifications(request):
    boss = SchoolAdminProfile.objects.filter(user=request.user).first()
    if boss is None:
        return Response({"detail": "Admins only."}, status=403)
    items = []
    waiting = Performance.objects.filter(
        student__school_id=boss.school_id, status="submitted").count()
    if waiting:
        items.append({
            "kind": "marks_awaiting_approval", "count": waiting,
            "message": f"{waiting} submitted marks are waiting for approval.",
        })
    since = timezone.now() - timedelta(days=DAYS)
    logs = [
        log for log in MarkAuditLog.objects.filter(
            school_id=boss.school_id, action="publish", timestamp__gte=since)
        if log.details.get("not_ranked")
    ]
    ids = [log.details["exam"] for log in logs if log.details.get("exam")]
    names = dict(Exam.objects.filter(id__in=ids).values_list("id", "name"))
    for log in logs:
        ranked = log.details["not_ranked"]
        exam_id = log.details.get("exam")
        name = names.get(exam_id, "an exam")
        items.append({
            "kind": "students_not_ranked", "exam_id": exam_id, "exam": name,
            "count": len(ranked), "admission_numbers": ranked,
            "timestamp": log.timestamp,
            "message": f"{len(ranked)} student(s) were not ranked in {name}.",
        })
    return Response({"count": len(items), "results": items})
