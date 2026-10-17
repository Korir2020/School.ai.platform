from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from schools.models import MarkAuditLog, School, SchoolAdminProfile

User = get_user_model()
URL = "/api/school/profile/"


class SchoolProfileTests(TestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="PA1")
        self.b = School.objects.create(
            name="B", code="PB1", location="City", county="Kisumu", school_type="primary")
        self.boss = self._admin("pbossa", self.a, False)
        self.dep = self._admin("pdepa", self.a, True)
        self.bossb = self._admin("pbossb", self.b, False)
        self.nobody = User.objects.create_user("pnobody", "pn@x.com", "pass12345")
        self.client = APIClient()

    def _admin(self, name, school, deputy):
        u = User.objects.create_user(name, f"{name}@x.com", "pass12345")
        SchoolAdminProfile.objects.create(user=u, school=school, is_deputy=deputy)
        return u

    def test_anonymous_blocked(self):
        self.assertIn(self.client.get(URL).status_code, (401, 403))
        self.assertIn(self.client.patch(URL, {}, format="json").status_code, (401, 403))

    def test_user_without_school_role_blocked(self):
        self.client.force_authenticate(self.nobody)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.patch(URL, {"county": "X"}, format="json").status_code, 403)

    def test_get_returns_own_school_only(self):
        self.client.force_authenticate(self.bossb)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "B")
        self.assertEqual(r.data["county"], "Kisumu")

    def test_admin_saves_profile_and_audit_logged(self):
        self.client.force_authenticate(self.boss)
        r = self.client.patch(URL, {
            "location": "  Town  ", "county": "Nairobi", "school_type": "Secondary"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.assertEqual(
            (self.a.location, self.a.county, self.a.school_type), ("Town", "Nairobi", "secondary"))
        self.assertEqual(
            MarkAuditLog.objects.filter(action="profile_updated", school=self.a).count(), 1)

    def test_partial_update_changes_only_sent_fields(self):
        self.client.force_authenticate(self.bossb)
        self.assertEqual(self.client.patch(URL, {"location": "Port"}, format="json").status_code, 200)
        self.b.refresh_from_db()
        self.assertEqual((self.b.location, self.b.county, self.b.school_type),
                         ("Port", "Kisumu", "primary"))

    def test_deputy_can_read_but_not_edit(self):
        self.client.force_authenticate(self.dep)
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.patch(URL, {"county": "X"}, format="json").status_code, 403)
        self.a.refresh_from_db()
        self.assertEqual(self.a.county, "")

    def test_other_school_is_never_touched(self):
        self.client.force_authenticate(self.boss)
        self.client.patch(URL, {"county": "Nairobi"}, format="json")
        self.b.refresh_from_db()
        self.assertEqual(self.b.county, "Kisumu")

    def test_bad_values_rejected_and_nothing_saved(self):
        self.client.force_authenticate(self.boss)
        for body in ({"school_type": "castle"}, {"county": "x" * 101},
                     {"location": "   "}, {"county": 5}):
            r = self.client.patch(URL, body, format="json")
            self.assertEqual(r.status_code, 400, body)
            self.assertIn("errors", r.data)
        self.a.refresh_from_db()
        self.assertEqual((self.a.location, self.a.county, self.a.school_type), ("", "", ""))
        self.assertFalse(MarkAuditLog.objects.filter(action="profile_updated").exists())

    def test_empty_body_rejected(self):
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.client.patch(URL, {}, format="json").status_code, 400)

    def test_saving_profile_ticks_setup_checklist(self):
        self.client.force_authenticate(self.boss)
        self.assertFalse(self.client.get("/api/setup/").data["checklist"]["profile"])
        self.client.patch(URL, {
            "location": "Town", "county": "Nairobi", "school_type": "secondary"}, format="json")
        self.assertTrue(self.client.get("/api/setup/").data["checklist"]["profile"])
