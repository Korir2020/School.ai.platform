"""Django email backend that sends through Brevo's HTTPS API (port 443).

Render's free plan blocks SMTP ports, so this avoids SMTP completely.
Select it with DJANGO_EMAIL_BACKEND=api.mail_backend.BrevoEmailBackend
and set DJANGO_BREVO_API_KEY. The sender address must be verified in Brevo.
"""
import json
import os
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = os.environ.get("DJANGO_BREVO_API_KEY", "")
        self.timeout = getattr(settings, "EMAIL_TIMEOUT", None) or 10

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise ImproperlyConfigured("DJANGO_BREVO_API_KEY is not set.")
        sent = 0
        for message in email_messages:
            try:
                self._send_one(message)
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent

    def _send_one(self, message):
        name, address = parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)
        if not address:
            raise ValueError("Email has no sender address.")
        if not message.to:
            raise ValueError("Email has no recipients.")
        sender = {"email": address}
        if name:
            sender["name"] = name
        payload = {
            "sender": sender,
            "to": [{"email": a} for a in message.to],
            "subject": message.subject,
            "textContent": message.body,
        }
        if message.cc:
            payload["cc"] = [{"email": a} for a in message.cc]
        if message.bcc:
            payload["bcc"] = [{"email": a} for a in message.bcc]
        request = urllib.request.Request(
            BREVO_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": self.api_key,
                "accept": "application/json",
                "content-type": "application/json",
                "user-agent": "marian-backend/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                if resp.status not in (200, 201, 202):
                    raise RuntimeError("Brevo returned status %s" % resp.status)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode("utf-8", "replace")
            raise RuntimeError("Brevo rejected the email (HTTP %s): %s" % (exc.code, detail)) from exc
