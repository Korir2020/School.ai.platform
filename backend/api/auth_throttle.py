from django.contrib.auth import get_user_model
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView


class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


def resolve_login_name(value):
    """Map a sign-in identifier to a username.

    A username always wins. An email is used only when it belongs to exactly
    one account, so a shared email can never sign anyone into the wrong account.
    """
    name = (value or "").strip()
    if "@" not in name:
        return name
    User = get_user_model()
    if User.objects.filter(username=name).exists():
        return name
    found = list(User.objects.filter(email__iexact=name).values_list("username", flat=True)[:2])
    return found[0] if len(found) == 1 else name


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginRateThrottle]

    def get_serializer(self, *args, **kwargs):
        data = kwargs.get("data")
        if data is not None and "username" in data:
            data = data.copy() if hasattr(data, "copy") else dict(data)
            data["username"] = resolve_login_name(data.get("username"))
            data.pop("remember", None)
            data.pop("mfa_code", None)
            kwargs["data"] = data
        return super().get_serializer(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        resp = super().post(request, *args, **kwargs)
        if resp.status_code != 200:
            return resp
        user = get_user_model().objects.filter(
            username=resolve_login_name(request.data.get("username"))).first()
        failure = second_step_failure(user, str(request.data.get("mfa_code", "") or ""))
        if failure:
            from rest_framework.response import Response
            return Response(failure, status=401)
        return resp


def second_step_failure(user, code):
    """Superadmins with MFA enabled must pass an authenticator or recovery code.

    Returns None when sign-in may proceed, else the error body. Recovery
    codes are single-use and removed once accepted.
    """
    if not user or not user.is_superuser:
        return None
    from django.contrib.auth.hashers import check_password
    from schools.models import MarkAuditLog, SuperadminSecurity
    from .totp import verify
    sec = SuperadminSecurity.objects.filter(user=user, mfa_enabled=True).first()
    if not sec:
        return None
    code = code.strip().replace(" ", "")
    if not code:
        return {"mfa_required": True, "detail": "Enter the code from your authenticator app."}
    if code.isdigit() and verify(sec.totp_secret, code):
        return None
    for h in list(sec.recovery_code_hashes or []):
        if check_password(code, h):
            sec.recovery_code_hashes = [x for x in sec.recovery_code_hashes if x != h]
            sec.save(update_fields=["recovery_code_hashes"])
            MarkAuditLog.objects.create(school=None, user=user, action="mfa_recovery_code_used")
            return None
    return {"mfa_required": True, "detail": "That code is not valid. Try the current code from your app."}
