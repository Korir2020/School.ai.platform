from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api import setup_views
from schools.models import (
    AcademicYear, MarkAuditLog, School, SchoolAdminProfile, Subject, Term,
)

User = get_user_model()
ALL = {k: True for k in ("profile", "academic_year", "term", "stream", "subject")}
STATUS = "/api/setup/"
COMPLETE = "/api/setup/complete/"


class SetupWizardTests(TestCase):
    def setUp(self):
        self.a = School.objects.create(
            name="A", code="SA1", location="Town", county="Nairobi", school_type="senior")
        self.b = School.objects.create(
            name="B", code="SB1", location="City", county="Kisumu", school_type="primary")
        self.boss = self._admin("bossa", self.a, False)
        self.dep = self._admin("depa", self.a, True)
        self.bossb = self._admin("bossb", self.b, False)
        self.nobody = User.objects.create_user("nobody", "n@x.com", "pass12345")
        self.client = APIClient()

    def _admin(self, name, school, deputy):
        u = User.objects.create_user(name, f"{name}@x.com", "pass12345")
        SchoolAdminProfile.objects.create(user=u, school=school, is_deputy=deputy)
        return u

    def _structure(self, school):
        y = AcademicYear.objects.create(
            school=school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        Term.objects.create(
            academic_year=y, name="T1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1))
        Subject.objects.create(school=school, name="Maths")

    def test_anonymous_blocked(self):
        self.assertIn(self.client.get(STATUS).status_code, (401, 403))
        self.assertIn(self.client.post(COMPLETE).status_code, (401, 403))

    def test_user_without_school_role_blocked(self):
        self.client.force_authenticate(self.nobody)
        self.assertEqual(self.client.get(STATUS).status_code, 403)
        self.assertEqual(self.client.post(COMPLETE).status_code, 403)

    def test_status_lists_missing_items(self):
        self.client.force_authenticate(self.boss)
        r = self.client.get(STATUS)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["setup_complete"])
        self.assertEqual(r.data["missing"], ["academic_year", "term", "stream", "subject"])

    def test_checklist_uses_real_records(self):
        self._structure(self.a)
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.client.get(STATUS).data["missing"], ["stream"])

    def test_deputy_can_view_but_not_complete(self):
        self.client.force_authenticate(self.dep)
        self.assertEqual(self.client.get(STATUS).status_code, 200)
        with mock.patch.object(setup_views, "compute_checklist", return_value=dict(ALL)):
            self.assertEqual(self.client.post(COMPLETE).status_code, 403)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.setup_completed_at)

    def test_incomplete_setup_cannot_complete(self):
        self.client.force_authenticate(self.boss)
        r = self.client.post(COMPLETE)
        self.assertEqual(r.status_code, 400)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.setup_completed_at)
        self.assertFalse(MarkAuditLog.objects.filter(action="setup_completed").exists())

    def test_complete_sets_timestamp_and_is_idempotent(self):
        self.client.force_authenticate(self.boss)
        with mock.patch.object(setup_views, "compute_checklist", return_value=dict(ALL)):
            self.assertEqual(self.client.post(COMPLETE).status_code, 200)
            self.assertEqual(self.client.post(COMPLETE).status_code, 200)
        self.a.refresh_from_db()
        self.assertIsNotNone(self.a.setup_completed_at)
        self.assertEqual(
            MarkAuditLog.objects.filter(action="setup_completed", school=self.a).count(), 1)

    def test_schools_are_isolated(self):
        self._structure(self.a)
        self.client.force_authenticate(self.bossb)
        r = self.client.get(STATUS)
        self.assertIn("academic_year", r.data["missing"])
        with mock.patch.object(setup_views, "compute_checklist", return_value=dict(ALL)):
            self.assertEqual(self.client.post(COMPLETE).status_code, 200)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertIsNone(self.a.setup_completed_at)
        self.assertIsNotNone(self.b.setup_completed_at)
        self.assertFalse(MarkAuditLog.objects.filter(action="setup_completed", school=self.a).exists())

    def test_me_reports_setup_complete(self):
        self.client.force_authenticate(self.boss)
        self.assertIs(self.client.get("/api/auth/me/").data["setup_complete"], False)
        with mock.patch.object(setup_views, "compute_checklist", return_value=dict(ALL)):
            self.client.post(COMPLETE)
        self.assertIs(self.client.get("/api/auth/me/").data["setup_complete"], True)
