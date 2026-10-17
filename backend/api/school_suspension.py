from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import MarkAuditLog, School, SuperadminSecurity
from .totp import verify

NO = "Only a system Superadmin may suspend or reinstate a school."
NEEDS_MFA = "Enroll MFA and provide a valid authenticator code before changing a school's status."


def _out(s):
    return {"id": s.id, "is_suspended": s.is_suspended,
            "suspended_at": s.suspended_at, "suspended_reason": s.suspended_reason}


@api_view(["PATCH"])
def school_suspension(request, pk):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return Response({"detail": NO}, status=403)
    security = SuperadminSecurity.objects.filter(user=request.user, mfa_enabled=True).first()
    if not security or not verify(security.totp_secret, str(request.data.get("mfa_code", ""))):
        return Response({"detail": NEEDS_MFA}, status=403)
    school = School.objects.filter(pk=pk).first()
    if school is None:
        return Response({"detail": "Not found."}, status=404)
    suspended = request.data.get("suspended")
    if not isinstance(suspended, bool):
        return Response({"detail": "suspended must be true or false."}, status=400)
    reason = str(request.data.get("reason") or "").strip()
    if suspended and len(reason) < 10:
        return Response({"detail": "Give a reason of at least 10 characters."}, status=400)
    with transaction.atomic():
        if suspended:
            school.is_suspended, school.suspended_at = True, timezone.now()
            school.suspended_reason, school.suspended_by = reason[:255], request.user
        else:
            school.is_suspended, school.suspended_at = False, None
            school.suspended_reason, school.suspended_by = "", None
        school.save(update_fields=["is_suspended", "suspended_at", "suspended_reason", "suspended_by"])
        MarkAuditLog.objects.create(
            school=None, user=request.user,
            action="school_suspended" if suspended else "school_reinstated",
            details={"school_id": school.id, "school_name": school.name, "reason": reason[:255]},
        )
    return Response(_out(school))
