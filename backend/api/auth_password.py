from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from .password_throttle import PasswordRateThrottle
from .session_cleanup import end_other_sessions


@api_view(["POST"])
@throttle_classes([PasswordRateThrottle])
def change_password(request):
    """Let the logged-in user change their own password."""
    old = request.data.get("old_password") or ""
    new = request.data.get("new_password") or ""
    user = request.user
    if not user.check_password(old):
        return Response({"detail": "Current password is wrong."}, status=400)
    if new == old:
        return Response({"detail": "New password must be different."}, status=400)
    try:
        validate_password(new, user)
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    user.set_password(new)
    user.save()
    end_other_sessions(user, request.data.get("refresh")
        or request.COOKIES.get("marian_rt"))
    return Response({"detail": "Password changed."})
