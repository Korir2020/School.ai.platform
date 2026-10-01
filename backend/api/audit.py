from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import MarkAuditLog, SchoolAdminProfile
from .permissions import get_user_school_id


@api_view(["GET"])
def audit_log_list(request):
    logs = MarkAuditLog.objects.select_related("user")
    if not request.user.is_superuser:
        if not SchoolAdminProfile.objects.filter(user=request.user).exists():
            return Response({"detail": "Admins only."}, status=403)
        logs = logs.filter(school_id=get_user_school_id(request.user))
    performance_id = request.query_params.get("performance")
    if performance_id and performance_id.isdigit():
        logs = logs.filter(performance_id=int(performance_id))
    return Response([
        {
            "id": log.id,
            "performance": log.performance_id,
            "user": log.user.username if log.user else None,
            "action": log.action,
            "details": log.details,
            "timestamp": log.timestamp,
        }
        for log in logs[:200]
    ])
