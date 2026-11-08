from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from schools.models import MarkAuditLog, SchoolAdminProfile, StaffProfile
from .permissions import get_user_school_id
from api.fee_permissions import get_fee_access_school_id


@api_view(["GET"])
def audit_log_list(request):
    logs = MarkAuditLog.objects.select_related("user")
    is_admin = SchoolAdminProfile.objects.filter(user=request.user).exists()
    is_bursar = StaffProfile.objects.filter(user=request.user, role="bursar").exists()
    if is_bursar and not is_admin and not request.user.is_superuser:
        try:
            school_id = get_fee_access_school_id(request.user)
        except PermissionDenied as exc:
            return Response({"detail": str(exc.detail)}, status=403)
        logs = logs.filter(school_id=school_id, action__startswith="fee_")
    elif not request.user.is_superuser:
        if not is_admin:
            return Response({"detail": "Admins only."}, status=403)
        school_id = get_user_school_id(request.user)
        logs = logs.filter(school_id=school_id)
        try:
            get_fee_access_school_id(request.user, school_id=school_id)
            fee_logs_allowed = True
        except PermissionDenied:
            fee_logs_allowed = False
        if not fee_logs_allowed:
            logs = logs.exclude(action__startswith="fee_")
    else:
        # Platform operators can retain the existing non-fee audit view, but
        # school fee amounts are never available to a platform superuser.
        logs = logs.exclude(action__startswith="fee_")
    performance_id = request.query_params.get("performance")
    if performance_id and performance_id.isdigit():
        logs = logs.filter(performance_id=int(performance_id))
    q = request.query_params
    if q.get("action"):
        logs = logs.filter(action=q["action"][:30])
    if q.get("user"):
        logs = logs.filter(user__username=q["user"])
    for key, lookup in (("date_from", "gte"), ("date_to", "lte")):
        d = parse_date(q.get(key, ""))
        if d:
            logs = logs.filter(**{"timestamp__date__" + lookup: d})
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
