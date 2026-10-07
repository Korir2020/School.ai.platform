"""Pluggable OTP delivery. There is NO SMS provider yet.
Returns True only if a code was really handed to a channel.
DEBUG prints to the server console (developer only); production returns
False: nothing is sent and we never pretend."""
from django.conf import settings


def deliver_otp(phone, code):
    if getattr(settings, "DEBUG", False):
        print(f"[DEV ONLY] verification code for {phone}: {code}")
        return True
    return False
