from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from schools.models import MarkAuditLog, SchoolRegistration

URL = "/api/school-registration/resend/"
PAYLOAD = {
    "school_name": "Resend High", "proposed_school_code": "RSH01", "school_type": "primary",
    "school_phone": "+254700000000", "county": "Nairobi",
    "administrator_name": "Ann Admin", "administrator_username": "annadmin",
    "administrator_email": "ann@example.com", "administrator_phone": "+254711111111",
    "password": "Str0ng!Passw0rd#2026", "confirm_password": "Str0ng!Passw0rd#2026",
    "authorized": True,
}


class ResendCodeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        r = self.client.post("/api/school-registration/", PAYLOAD, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.ref = r.data["reference"]
        self.body = {"reference": self.ref, "username": "annadmin"}
        mail.outbox.clear()
        cache.clear()

    def _age(self, **fields):
        fields.setdefault("otp_sent_at", timezone.now() - timedelta(seconds=61))
        SchoolRegistration.objects.filter(reference=self.ref).update(**fields)

    def _reg(self):
        return SchoolRegistration.objects.get(reference=self.ref)

    def test_resend_sends_fresh_code_and_audits(self):
        self._age()
        old_hash = self._reg().otp_hash
        r = self.client.post(URL, self.body, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self._reg().otp_send_count, 2)
        self.assertNotEqual(self._reg().otp_hash, old_hash)
        self.assertEqual(MarkAuditLog.objects.filter(action="school_reg_resent").count(), 1)

    def test_cooldown_blocks_second_send(self):
        r = self.client.post(URL, self.body, format="json")
        self.assertEqual(r.status_code, 429)
        self.assertIn("retry_after", r.data)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self._reg().otp_send_count, 1)

    def test_total_send_cap(self):
        self._age(otp_send_count=5)
        r = self.client.post(URL, self.body, format="json")
        self.assertEqual(r.status_code, 429)
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_or_missing_details_get_same_404(self):
        self._age()
        for body in ({"reference": self.ref, "username": "someoneelse"},
                     {"reference": "NOPE", "username": "annadmin"},
                     {"reference": self.ref}, {}):
            cache.clear()
            r = self.client.post(URL, body, format="json")
            self.assertEqual(r.status_code, 404, body)
        self.assertEqual(len(mail.outbox), 0)

    def test_verified_registration_cannot_resend(self):
        self._age(status="verified")
        self.assertEqual(self.client.post(URL, self.body, format="json").status_code, 409)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_not_configured_returns_503(self):
        self._age()
        with mock.patch("api.resend_views._send_registration_otp", side_effect=RuntimeError):
            r = self.client.post(URL, self.body, format="json")
        self.assertEqual(r.status_code, 503)
        self.assertFalse(MarkAuditLog.objects.filter(action="school_reg_resent").exists())

    def test_username_match_ignores_case(self):
        self._age()
        r = self.client.post(URL, {"reference": self.ref.lower(), "username": "ANNADMIN"}, format="json")
        self.assertEqual(r.status_code, 200)
