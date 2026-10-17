from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import MarkAuditLog, School, SchoolAdminProfile, SuperadminSecurity
from .suspension import school_for_user, suspended_school_for

PW = "Xk9-secure-pass"
GOOD = {"suspended": True, "reason": "Fraud investigation", "mfa_code": "123456"}


class SchoolSuspensionTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.root = User.objects.create_superuser("root", "r@example.com", PW)
        SuperadminSecurity.objects.create(user=self.root, mfa_enabled=True, totp_secret="x")
        self.boss = User.objects.create_user("boss", password=PW)
        SchoolAdminProfile.objects.create(user=self.boss, school=self.a)
        p = patch("api.school_suspension.verify", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def patch_school(self, s, data, who=None):
        if who:
            self.client.force_authenticate(who)
        return self.client.patch(f"/api/schools/{s.id}/suspension/", data, format="json")

    def test_school_admin_cannot_suspend(self):
        r = self.patch_school(self.a, GOOD, self.boss)
        self.assertEqual(r.status_code, 403)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_suspended)

    def test_anonymous_rejected(self):
        self.assertIn(self.patch_school(self.a, GOOD).status_code, (401, 403))

    def test_bad_mfa_code_rejected(self):
        with patch("api.school_suspension.verify", return_value=False):
            r = self.patch_school(self.a, GOOD, self.root)
        self.assertEqual(r.status_code, 403)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_suspended)

    def test_superadmin_without_mfa_rejected(self):
        other = User.objects.create_superuser("root2", "r2@example.com", PW)
        r = self.patch_school(self.a, GOOD, other)
        self.assertEqual(r.status_code, 403)

    def test_reason_required(self):
        r = self.patch_school(self.a, {**GOOD, "reason": "short"}, self.root)
        self.assertEqual(r.status_code, 400)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_suspended)

    def test_flag_must_be_boolean(self):
        r = self.patch_school(self.a, {**GOOD, "suspended": "yes"}, self.root)
        self.assertEqual(r.status_code, 400)

    def test_suspend_then_reinstate_only_that_school_with_audit(self):
        r = self.patch_school(self.a, GOOD, self.root)
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertTrue(self.a.is_suspended)
        self.assertFalse(self.b.is_suspended)
        self.assertEqual(self.a.suspended_by, self.root)
        log = MarkAuditLog.objects.get(action="school_suspended")
        self.assertIsNone(log.school)
        self.assertEqual(log.details["school_id"], self.a.id)
        r = self.patch_school(self.a, {"suspended": False, "mfa_code": "123456"}, self.root)
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_suspended)
        self.assertEqual(self.a.suspended_reason, "")
        self.assertEqual(MarkAuditLog.objects.filter(action="school_reinstated").count(), 1)

    def test_helper_finds_users_school(self):
        self.assertEqual(school_for_user(self.boss), self.a)
        self.assertIsNone(school_for_user(self.root))
        self.assertIsNone(suspended_school_for(self.boss))
        self.a.is_suspended = True
        self.a.save()
        self.assertEqual(suspended_school_for(self.boss), self.a)

    def test_suspended_school_blocked_on_normal_endpoint(self):
        self.client.force_authenticate(self.boss)
        self.assertNotEqual(self.client.get("/api/dashboard/").status_code, 403)
        self.a.is_suspended = True
        self.a.save()
        r = self.client.get("/api/dashboard/")
        self.assertEqual(r.status_code, 403)
        self.assertIn("suspended", str(r.data.get("detail", "")).lower())
        self.a.is_suspended = False
        self.a.save()
        self.assertNotEqual(self.client.get("/api/dashboard/").status_code, 403)
