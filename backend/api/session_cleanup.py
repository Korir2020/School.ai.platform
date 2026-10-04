from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken, OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken


def end_other_sessions(user, keep_refresh=None):
    """Blacklist all of the user's refresh tokens except keep_refresh,
    which is kept only if it is valid and really belongs to this user."""
    keep = None
    if isinstance(keep_refresh, str) and keep_refresh:
        try:
            tok = RefreshToken(keep_refresh)
            if str(tok.get("user_id")) == str(user.pk):
                keep = tok["jti"]
        except TokenError:
            keep = None
    rows = OutstandingToken.objects.filter(user=user)
    if keep:
        rows = rows.exclude(jti=keep)
    for row in rows:
        BlacklistedToken.objects.get_or_create(token=row)
