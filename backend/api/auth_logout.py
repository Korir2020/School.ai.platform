from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def logout(request):
    """Blacklist a refresh token. Holding the token is the proof."""
    token = request.data.get("refresh")
    if not token:
        return Response({"detail": "refresh token required."}, status=400)
    try:
        RefreshToken(token).blacklist()
    except TokenError:
        return Response({"detail": "Invalid or expired token."}, status=400)
    return Response(status=205)
