from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from schools.models import (
    JoinRequest, MarkAuditLog, SchoolAdminProfile, StaffProfile, TeacherProfile)
from . import join_codes
from .join_throttle import JoinCodeThrottle

MSG = {
    "pending": ("Your request is waiting for approval "
                "from your school administrator."),
    "approved": ("Your request has been approved. "
                 "Enter the invitation code to complete joining."),
    "rejected": "Your request was not approved. Contact your school administrator.",
    "joined": "You have successfully joined the school.",
}
BAD = "This invitation code is invalid or has expired."


def _bad(text, code=400):
    return Response({"detail": text}, status=code)


@api_view(["GET"])
def join_my_request(request):
    r = JoinRequest.objects.filter(user=request.user).select_related(
        "school").order_by("-requested_at").first()
    if r is None:
        return Response({"status": "none"})
    return Response({"status": r.status, "role": r.role,
                     "school": r.school.name, "message": MSG[r.status]})


def _has_profile(user):
    return (TeacherProfile.objects.filter(user=user).exists()
            or SchoolAdminProfile.objects.filter(user=user).exists()
            or StaffProfile.objects.filter(user=user).exists())


def _make_profile(r):
    if r.role == "teacher":
        TeacherProfile.objects.create(user=r.user, school=r.school)
    else:
        StaffProfile.objects.create(user=r.user, school=r.school, role=r.role)


def _used_before(user, code):
    j = JoinRequest.objects.filter(user=user, status="joined").first()
    inv = getattr(j, "invitation", None) if j else None
    return bool(inv) and join_codes.same(code, inv.code)


@api_view(["POST"])
@throttle_classes([JoinCodeThrottle])
def join_complete(request):
    code = str(request.data.get("code", ""))
    with transaction.atomic():
        r = JoinRequest.objects.select_for_update().select_related(
            "school").filter(user=request.user, status="approved").first()
        if r is None:
            if _used_before(request.user, code):
                return _bad("This invitation code has already been used.")
            return _bad("You have no approved request to complete.")
        inv = getattr(r, "invitation", None)
        if inv is None or not join_codes.same(code, inv.code):
            return _bad(BAD)
        now = timezone.now()
        if inv.used_at is not None or inv.expires_at <= now:
            return _bad(BAD)
        if _has_profile(request.user):
            return _bad("This account already belongs to a school.", 409)
        _make_profile(r)
        inv.used_at = now
        inv.save()
        r.status, r.joined_at = "joined", now
        r.save()
        MarkAuditLog.objects.create(
            school=r.school, user=request.user, action="join_completed",
            details={"username": request.user.username, "role": r.role})
    return Response({"school": {"id": r.school.id, "name": r.school.name},
                     "role": r.role, "detail": MSG["joined"]})
