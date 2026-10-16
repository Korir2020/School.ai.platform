import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from schools.models import MarkAuditLog, School, SchoolRegistration
from .join_throttle import SchoolRegisterThrottle, SchoolRegStatusThrottle

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,19}$")
PHONE_RE = re.compile(r"^\+?[0-9]{9,15}$")
USERNAME_RE = re.compile(r"^[\w.@+-]{3,150}$")
TYPES = {t for t, _ in SchoolRegistration.TYPES}
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
STATUS_TEXT = {
    "pending_verification": "Waiting for administrator email verification.",
    "verified": "Email verified.",
    "pending_approval": "Marian is reviewing your registration.",
    "needs_information": "Additional information required.",
    "approved": "Approved. You can sign in.",
    "rejected": "Your school registration was not approved.",
}


def clean_phone(value):
    return re.sub(r"[\s().-]", "", str(value or ""))


def new_reference():
    for _ in range(10):
        ref = "MSR-" + "".join(secrets.choice(ALPHABET) for _ in range(8))
        if not SchoolRegistration.objects.filter(reference=ref).exists():
            return ref
    raise RuntimeError("Could not make a reference.")


def code_available(code, exclude_pk=None):
    if School.objects.filter(code__iexact=code).exists():
        return False
    rows = SchoolRegistration.objects.filter(
        proposed_school_code__iexact=code, status__in=SchoolRegistration.OPEN)
    if exclude_pk:
        rows = rows.exclude(pk=exclude_pk)
    return not rows.exists()


def validate_submission(d):
    """Return (clean_data, password, errors). errors is field -> message."""
    err = {}
    g = lambda k: str(d.get(k, "") or "").strip()
    c = {k: g(k) for k in (
        "school_name", "school_type", "school_email", "county", "sub_county",
        "address", "administrator_name", "administrator_username",
        "administrator_email")}
    c["proposed_school_code"] = g("proposed_school_code").upper()
    c["school_phone"] = clean_phone(d.get("school_phone"))
    c["administrator_phone"] = clean_phone(d.get("administrator_phone"))
    return c, err


REQUIRED = (
    ("school_name", "School name"), ("county", "County"),
    ("administrator_name", "Full name"), ("administrator_username", "Username"),
    ("administrator_email", "Administrator email"),
    ("school_phone", "School phone"), ("administrator_phone", "Phone"),
    ("proposed_school_code", "School Code"), ("school_type", "School type"))


def check_fields(c, d, err):
    for k, label in REQUIRED:
        if not c[k]:
            err[k] = f"{label} is required."
    if len(c["school_name"]) > 200:
        err["school_name"] = "School name is too long."
    if "proposed_school_code" not in err and not CODE_RE.match(
            c["proposed_school_code"]):
        err["proposed_school_code"] = (
            "Use 3-20 letters, numbers, - or _ (start with a letter or number).")
    if "school_type" not in err and c["school_type"] not in TYPES:
        err["school_type"] = "Choose a school type."
    for k in ("school_phone", "administrator_phone"):
        if k not in err and not PHONE_RE.match(c[k]):
            err[k] = "Enter a valid phone number."
    for k in ("school_email", "administrator_email"):
        if c[k]:
            try:
                validate_email(c[k])
            except ValidationError:
                err[k] = "Enter a valid email address."
    if "administrator_username" not in err and not USERNAME_RE.match(
            c["administrator_username"]):
        err["administrator_username"] = "Username: 3+ letters, numbers or . _ @ + -"
    if str(d.get("authorized")).lower() not in ("true", "1"):
        err["authorized"] = "You must confirm you are authorized."


def check_password_and_unique(c, d, err):
    pw, pw2 = str(d.get("password", "")), str(d.get("confirm_password", ""))
    if not pw:
        err["password"] = "Password is required."
    elif pw != pw2:
        err["confirm_password"] = "Passwords do not match."
    else:
        try:
            validate_password(pw, User(
                username=c["administrator_username"],
                email=c["administrator_email"],
                first_name=c["administrator_name"][:150]))
        except ValidationError as e:
            err["password"] = " ".join(e.messages)
    if "proposed_school_code" not in err and not code_available(
            c["proposed_school_code"]):
        err["proposed_school_code"] = "That School Code is not available."
    u = c["administrator_username"]
    if "administrator_username" not in err and (
            User.objects.filter(username__iexact=u).exists()
            or SchoolRegistration.objects.filter(
                administrator_username__iexact=u,
                status__in=SchoolRegistration.OPEN).exists()):
        err["administrator_username"] = "That username is taken."
    return pw


def _send_registration_otp(reg):
    if not settings.DEBUG and settings.EMAIL_BACKEND == "django.core.mail.backends.dummy.EmailBackend":
        raise RuntimeError("Registration email delivery is not configured")
    code = f"{secrets.randbelow(1_000_000):06d}"
    reg.otp_hash = make_password(code)
    reg.otp_expires_at = timezone.now() + timedelta(minutes=10)
    reg.otp_attempts = 0
    reg.otp_send_count += 1
    reg.otp_sent_at = timezone.now()
    reg.save(update_fields=["otp_hash", "otp_expires_at", "otp_attempts", "otp_send_count", "otp_sent_at", "updated_at"])
    send_mail(
        "Verify your Marian school registration",
        f"Your Marian verification code is {code}. It expires in 10 minutes. If you did not request this, ignore this email.",
        getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@marian.local"),
        [reg.administrator_email], fail_silently=False,
    )


def applicant_view(reg):
    """Only what the applicant may see: no notes, no hashes."""
    out = {"reference": reg.reference, "school_name": reg.school_name,
           "status": reg.status, "status_text": STATUS_TEXT[reg.status],
           "verification_status": reg.verification_status}
    if reg.status == "needs_information":
        out["info_request_message"] = reg.info_request_message
    if reg.status == "rejected":
        out["rejection_reason"] = reg.rejection_reason
    return out


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([SchoolRegisterThrottle])
def school_register(request):
    d = request.data
    c, err = validate_submission(d)
    check_fields(c, d, err)
    pw = check_password_and_unique(c, d, err)
    bad = {"detail": "Please fix the highlighted fields.", "errors": err}
    if err:
        return Response(bad, status=400)
    try:
        with transaction.atomic():
            reg = SchoolRegistration.objects.create(
                reference=new_reference(), password_hash=make_password(pw),
                authorization_confirmed_at=timezone.now(), **c)
            MarkAuditLog.objects.create(
                school=None, user=None, action="school_reg_submitted",
                details={"reference": reg.reference,
                         "school_code": reg.proposed_school_code})
            _send_registration_otp(reg)
    except IntegrityError:
        bad["errors"] = {"proposed_school_code": "That School Code is not available."}
        return Response(bad, status=400)
    except RuntimeError:
        return Response({"detail": "School registration email delivery is not configured."}, status=503)
    return Response(applicant_view(reg), status=201)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([SchoolRegStatusThrottle])
@extend_schema(responses={200: OpenApiResponse(description="Applicant email verified."), 400: OpenApiResponse(description="Invalid or expired verification code."), 429: OpenApiResponse(description="Too many verification attempts.")})
def school_register_verify(request):
    ref = str(request.data.get("reference", "")).strip().upper()
    code = str(request.data.get("code", "")).strip()
    reg = SchoolRegistration.objects.filter(reference=ref).first()
    if reg is None or reg.status != "pending_verification":
        return Response({"detail": "The verification code is invalid or expired."}, status=400)
    if reg.otp_attempts >= 5 or not reg.otp_expires_at or reg.otp_expires_at <= timezone.now():
        return Response({"detail": "The verification code is invalid or expired."}, status=400)
    reg.otp_attempts += 1
    if not re.fullmatch(r"\d{6}", code) or not check_password(code, reg.otp_hash):
        reg.save(update_fields=["otp_attempts", "updated_at"])
        return Response({"detail": "The verification code is invalid or expired."}, status=400)
    reg.status = "verified"
    reg.verification_status = "verified"
    reg.verified_at = timezone.now()
    reg.otp_hash = ""
    reg.save(update_fields=["status", "verification_status", "verified_at", "otp_hash", "otp_attempts", "updated_at"])
    MarkAuditLog.objects.create(school=None, user=None, action="school_admin_verified",
                                details={"reference": reg.reference})
    return Response(applicant_view(reg))


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([SchoolRegStatusThrottle])
def school_register_status(request):
    ref = str(request.data.get("reference", "")).strip().upper()
    user = str(request.data.get("username", "")).strip()
    reg = SchoolRegistration.objects.filter(
        reference=ref, administrator_username__iexact=user).first()
    if reg is None:
        return Response({"detail": "Registration not found."}, status=404)
    return Response(applicant_view(reg))


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([SchoolRegStatusThrottle])
def school_register_respond(request):
    ref = str(request.data.get("reference", "")).strip().upper()
    user = str(request.data.get("username", "")).strip()
    message = str(request.data.get("message", "")).strip()
    reg = SchoolRegistration.objects.filter(reference=ref, administrator_username__iexact=user).first()
    if reg is None:
        return Response({"detail": "Registration not found."}, status=404)
    if not message:
        return Response({"detail": "Please write your reply."}, status=400)
    if len(message) > 2000:
        return Response({"detail": "Your reply is too long (2000 characters at most)."}, status=400)
    with transaction.atomic():
        reg = SchoolRegistration.objects.select_for_update().get(pk=reg.pk)
        if reg.status != "needs_information":
            return Response({"detail": "No information has been requested for this application."}, status=409)
        reg.info_response_message = message
        reg.status = "pending_approval"
        reg.save(update_fields=["info_response_message", "status", "updated_at"])
        MarkAuditLog.objects.create(school=None, user=None, action="school_reg_info_reply", details={"reference": reg.reference})
    return Response(applicant_view(reg))
