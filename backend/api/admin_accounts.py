from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import MarkAuditLog, SchoolAdminProfile
from .session_cleanup import end_other_sessions

NO = "You are not allowed to do that."


def _row(p):
    return {"id": p.id, "username": p.user.username, "school": p.school.name,
            "is_deputy": p.is_deputy, "is_active": p.user.is_active}


@api_view(["GET"])
def admin_account_list(request):
    if not request.user.is_superuser:
        return Response({"detail": "Only a superuser can list administrators."}, status=403)
    rows = SchoolAdminProfile.objects.select_related("user", "school").order_by("school__name", "id")
    return Response({"results": [_row(p) for p in rows]})


@api_view(["POST"])
def admin_reset_password(request, pk):
    root = request.user.is_superuser
    me = SchoolAdminProfile.objects.filter(user=request.user).first()
    if not root and (me is None or me.is_deputy):
        return Response({"detail": NO}, status=403)
    t = SchoolAdminProfile.objects.filter(pk=pk).select_related("user").first()
    if t is not None and not root and t.school_id != me.school_id:
        t = None
    if t is None:
        return Response({"detail": "Not found."}, status=404)
    if not root and not t.is_deputy:
        return Response({"detail": NO}, status=403)
    pw = str(request.data.get("password", ""))
    try:
        validate_password(pw, t.user)
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    with transaction.atomic():
        t.user.set_password(pw)
        t.user.save(update_fields=["password"])
        end_other_sessions(t.user)
        MarkAuditLog.objects.create(
            school_id=t.school_id, user=request.user, action="admin_password_reset",
            details={"account": t.user.username})
    return Response({"detail": "Password reset."})
