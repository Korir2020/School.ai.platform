import secrets
from datetime import timedelta

from django.utils import timezone

from schools.models import InvitationCode

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
VALID_DAYS = 7


def new_code():
    while True:
        tail = "".join(secrets.choice(ALPHABET) for _ in range(6))
        code = "MARIAN-" + tail
        if not InvitationCode.objects.filter(code=code).exists():
            return code


def expiry():
    return timezone.now() + timedelta(days=VALID_DAYS)


def same(a, b):
    a, b = str(a).strip().upper(), str(b).strip().upper()
    return secrets.compare_digest(a.encode(), b.encode())
