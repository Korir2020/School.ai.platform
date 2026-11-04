"""Pluggable OTP delivery.
Returns True only if a code was really handed to a channel.
With an SMS provider configured (see api/sms.py) the code goes out by SMS.
Without one, DEBUG prints to the server console (developer only) and
production returns False: nothing is sent and we never pretend."""
from django.conf import settings

from . import sms


def deliver_otp(phone, code):
    if sms.is_configured() and sms.provider() != "console":
        status, _ = sms.send_one(phone, f"Your Marian verification code is {code}. It expires in 10 minutes.")
        return status == "sent"
    if getattr(settings, "DEBUG", False):
        print(f"[DEV ONLY] verification code for {phone}: {code}")
        return True
    return False
