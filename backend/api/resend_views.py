import math

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from schools.models import MarkAuditLog, SchoolRegistration
from .join_throttle import SchoolRegStatusThrottle
from .school_registration import _send_registration_otp, applicant_view

COOLDOWN_SECONDS = 60
MAX_SENDS = 5
NOT_FOUND = {"detail": "Registration not found."}


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([SchoolRegStatusThrottle])
def school_register_resend(request):
    ref = str(request.data.get("reference", "")).strip().upper()
    user = str(request.data.get("username", "")).strip()
    if not ref or not user:
        return Response(NOT_FOUND, status=404)
    with transaction.atomic():
        reg = (
            SchoolRegistration.objects.select_for_update()
            .filter(reference=ref, administrator_username__iexact=user)
            .first()
        )
        if reg is None:
            return Response(NOT_FOUND, status=404)
        if reg.status != "pending_verification":
            return Response(
                {"detail": "This registration no longer needs a code."}, status=409)
        if reg.otp_send_count >= MAX_SENDS:
            return Response(
                {"detail": "Too many codes were sent. Contact Marian support."}, status=429)
        if reg.otp_sent_at:
            wait = COOLDOWN_SECONDS - (timezone.now() - reg.otp_sent_at).total_seconds()
            if wait > 0:
                return Response(
                    {"detail": f"Wait {math.ceil(wait)} seconds before requesting another code.",
                     "retry_after": math.ceil(wait)}, status=429)
        try:
            _send_registration_otp(reg)
        except RuntimeError:
            return Response(
                {"detail": "School registration email delivery is not configured."}, status=503)
        MarkAuditLog.objects.create(
            school=None, user=None, action="school_reg_resent",
            details={"reference": reg.reference, "send_count": reg.otp_send_count})
    return Response(applicant_view(reg))
