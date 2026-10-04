from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken, OutstandingToken,
)

from schools.models import MarkAuditLog, SchoolAdminProfile, TeacherProfile

NO = "Only school admins can manage teacher accounts."


def _find(request, pk):
    admin = SchoolAdminProfile.objects.filter(user=request.user).first()
    if admin is None:
        return None, Response({"detail": NO}, status=403)
    t = TeacherProfile.objects.filter(
        pk=pk, school_id=admin.school_id).select_related("user").first()
    if t is None:
        return None, Response({"detail": "Not found."}, status=404)
    return (admin, t), None


def _log(admin, t, action):
    MarkAuditLog.objects.create(
        school_id=admin.school_id, user=admin.user, action=action,
        details={"teacher": t.user.username})


@api_view(["PATCH"])
def teacher_detail(request, pk):
    found, err = _find(request, pk)
    if err:
        return err
    admin, t = found
    flag = request.data.get("is_active")
    if not isinstance(flag, bool):
        return Response({"detail": "is_active must be true or false."}, status=400)
    with transaction.atomic():
        t.user.is_active = flag
        t.user.save(update_fields=["is_active"])
        _log(admin, t, "teacher_activated" if flag else "teacher_deactivated")
    return Response({"id": t.id, "is_active": flag})


@api_view(["POST"])
def teacher_reset_password(request, pk):
    found, err = _find(request, pk)
    if err:
        return err
    admin, t = found
    pw = str(request.data.get("password", ""))
    try:
        validate_password(pw, t.user)
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    with transaction.atomic():
        t.user.set_password(pw)
        t.user.save(update_fields=["password"])
        for tok in OutstandingToken.objects.filter(user=t.user):
            BlacklistedToken.objects.get_or_create(token=tok)
        _log(admin, t, "teacher_password_reset")
    return Response({"detail": "Password reset."})
