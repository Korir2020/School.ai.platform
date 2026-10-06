from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    InvitationCode, JoinRequest, MarkAuditLog, SchoolAdminProfile)
from . import join_codes
from .notify import notify_user

NO = "Only school admins can do this."


def _boss(request):
    return SchoolAdminProfile.objects.filter(user=request.user).first()


def _row(r):
    inv = getattr(r, "invitation", None)
    show = bool(inv) and r.status == "approved" and inv.used_at is None
    return {
        "id": r.id, "username": r.user.username, "role": r.role,
        "name": r.user.get_full_name() or r.user.username,
        "status": r.status, "requested_at": r.requested_at,
        "code": inv.code if show else None,
        "code_expires_at": inv.expires_at if show else None}


@api_view(["GET"])
def join_request_list(request):
    boss = _boss(request)
    if boss is None:
        return Response({"detail": NO}, status=403)
    rows = JoinRequest.objects.filter(school_id=boss.school_id)
    status = request.query_params.get("status")
    if status:
        rows = rows.filter(status=status)
    rows = rows.select_related("user", "invitation")
    return Response({"results": [_row(r) for r in rows.order_by("-requested_at")]})


def _issue(r, actor):
    inv = InvitationCode.objects.filter(request=r).first()
    if inv is None:
        inv = InvitationCode(request=r, school=r.school)
    inv.code, inv.expires_at = join_codes.new_code(), join_codes.expiry()
    inv.created_by, inv.used_at = actor, None
    inv.save()
    return inv


def _decide(request, pk, approve):
    boss = _boss(request)
    if boss is None:
        return Response({"detail": NO}, status=403)
    with transaction.atomic():
        r = JoinRequest.objects.select_for_update().filter(
            pk=pk, school_id=boss.school_id).first()
        if r is None:
            return Response({"detail": "Not found."}, status=404)
        if r.status not in (("pending", "approved") if approve else ("pending",)):
            return Response({"detail": f"Request is already {r.status}."}, status=409)
        r.status = "approved" if approve else "rejected"
        r.decided_by, r.decided_at = request.user, timezone.now()
        r.save()
        out = {"id": r.id, "status": r.status}
        if approve:
            inv = _issue(r, request.user)
            out.update(code=inv.code, expires_at=inv.expires_at)
        MarkAuditLog.objects.create(
            school_id=boss.school_id, user=request.user,
            action="join_approved" if approve else "join_rejected",
            details={"username": r.user.username, "role": r.role})
        if approve:
            text = ("Your request was approved. Ask your school "
                    "administrator for your invitation code.")
        else:
            text = "Your request was not approved."
        notify_user(
            boss.school, r.user, "join_approved" if approve
            else "join_rejected", text, r)
    return Response(out)


@api_view(["POST"])
def join_request_approve(request, pk):
    return _decide(request, pk, True)


@api_view(["POST"])
def join_request_reject(request, pk):
    return _decide(request, pk, False)
