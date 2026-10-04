from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from .auth_cookie import COOKIE, origin_ok

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def logout(request):
    token = request.data.get("refresh")
    if not token and not origin_ok(request):
        return Response({"detail": "Bad origin."}, status=403)
    token = token or request.COOKIES.get(COOKIE)
    if not token:
        return Response({"detail": "refresh token required."}, status=400)
    try:
        RefreshToken(token).blacklist()
    except TokenError:
        return Response({"detail": "Invalid or expired token."}, status=400)
    resp = Response(status=205)
    resp.delete_cookie(COOKIE, path="/api/auth/", samesite="Lax")
    return resp
