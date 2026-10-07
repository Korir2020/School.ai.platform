from unittest import mock

from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APITestCase

from schools.models import (
    MarkAuditLog, School, SchoolAdminProfile, SchoolRegistration)
from .join_throttle import SchoolRegisterThrottle

PW = "Xk9-secure-pass"
URL = "/api/school-registration/"
STATUS = "/api/school-registration/status/"


def good(**over):
    d = {
        "school_name": "Sunrise Academy", "proposed_school_code": "sunrise-01",
        "school_type": "secondary", "school_phone": "0712 345 678",
        "school_email": "", "county": "Nairobi", "sub_county": "",
        "address": "", "administrator_name": "Jane Doe",
        "administrator_username": "janedoe", "administrator_email": "",
        "administrator_phone": "+254712345678", "password": PW,
        "confirm_password": PW, "authorized": True}
    d.update(over)
    return d


class SubmitTests(APITestCase):
    def setUp(self):
        cache.clear()

    def post(self, **over):
        return self.client.post(URL, good(**over), format="json")

    def test_valid_creates_only_a_registration(self):
        r = self.post()
        self.assertEqual(r.status_code, 201, r.content)
        reg = SchoolRegistration.objects.get()
        self.assertEqual(reg.status, "pending_verification")
        self.assertEqual(reg.proposed_school_code, "SUNRISE-01")
        self.assertEqual(School.objects.count(), 0)
        self.assertFalse(User.objects.filter(username="janedoe").exists())
        self.assertEqual(SchoolAdminProfile.objects.count(), 0)

    def test_password_hashed_never_returned(self):
        r = self.post()
        reg = SchoolRegistration.objects.get()
        self.assertNotEqual(reg.password_hash, PW)
        self.assertTrue(check_password(PW, reg.password_hash))
        self.assertNotIn(PW, r.content.decode())
        self.assertNotIn("password_hash", r.data)

    def test_missing_required_fields(self):
        r = self.client.post(URL, {}, format="json")
        self.assertEqual(r.status_code, 400)
        for k in ("school_name", "proposed_school_code", "school_type",
                  "school_phone", "county", "administrator_name",
                  "administrator_username", "administrator_phone",
                  "password", "authorized"):
            self.assertIn(k, r.data["errors"], k)
        self.assertEqual(SchoolRegistration.objects.count(), 0)

    def test_checkbox_required(self):
        self.assertIn("authorized", self.post(authorized=False).data["errors"])

    def test_invalid_school_code(self):
        for bad in ("ab", "has space", "bad!code", "-start", "x" * 21):
            r = self.post(proposed_school_code=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("proposed_school_code", r.data["errors"])

    def test_duplicate_code_school_and_open_registration(self):
        School.objects.create(name="X", code="Sunrise-01")
        self.assertEqual(self.post().status_code, 400)
        School.objects.all().delete()
        self.assertEqual(self.post().status_code, 201)
        r = self.post(administrator_username="other")
        self.assertIn("proposed_school_code", r.data["errors"])

    def test_rejected_registration_frees_code(self):
        self.post()
        SchoolRegistration.objects.update(status="rejected")
        self.assertEqual(self.post().status_code, 201)

    def test_duplicate_username(self):
        User.objects.create_user("JaneDoe", password=PW)
        r = self.post()
        self.assertIn("administrator_username", r.data["errors"])

    def test_weak_and_mismatched_passwords(self):
        r = self.post(password="12345678", confirm_password="12345678")
        self.assertIn("password", r.data["errors"])
        r = self.post(confirm_password=PW + "x")
        self.assertIn("confirm_password", r.data["errors"])

    def test_bad_phone_email_type(self):
        r = self.post(school_phone="abc", administrator_email="nope",
                      school_type="hacker")
        for k in ("school_phone", "administrator_email", "school_type"):
            self.assertIn(k, r.data["errors"])

    def test_throttled(self):
        rates = {"school_register": "2/min"}
        with mock.patch.object(SchoolRegisterThrottle, "THROTTLE_RATES", rates):
            cache.clear()
            codes = [self.post(proposed_school_code=f"CODE-{i}",
                               administrator_username=f"user{i}").status_code
                     for i in range(3)]
        self.assertEqual(codes, [201, 201, 429])

    def test_audit_has_no_school_and_no_secret(self):
        self.post()
        log = MarkAuditLog.objects.get(action="school_reg_submitted")
        self.assertIsNone(log.school)
        self.assertNotIn(PW, str(log.details))


class StatusTests(APITestCase):
    def setUp(self):
        cache.clear()
        r = self.client.post(URL, good(), format="json")
        self.ref = r.data["reference"]

    def status(self, ref, user):
        return self.client.post(
            STATUS, {"reference": ref, "username": user}, format="json")

    def test_applicant_reads_status(self):
        r = self.status(self.ref, "JANEDOE")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "pending_verification")

    def test_wrong_reference_or_username_404(self):
        self.assertEqual(self.status("MSR-NOPE0000", "janedoe").status_code, 404)
        self.assertEqual(self.status(self.ref, "other").status_code, 404)

    def test_no_internal_data_leaks(self):
        SchoolRegistration.objects.update(
            internal_notes="SECRET NOTE", status="rejected",
            rejection_reason="Not eligible")
        body = self.status(self.ref, "janedoe").content.decode()
        self.assertNotIn("SECRET NOTE", body)
        self.assertNotIn("password", body)
        self.assertIn("Not eligible", body)

    def test_registration_gives_no_login_or_data_access(self):
        r = self.client.post("/api/auth/login/", {
            "username": "janedoe", "password": PW}, format="json")
        self.assertIn(r.status_code, (400, 401))
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/students/").status_code, 401)
