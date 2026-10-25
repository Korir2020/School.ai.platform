from rest_framework.test import APITestCase

from api import tests as base
from api.report_source import DjangoDataSource

URL = "/api/school/branding/"


class SchoolMottoTests(APITestCase):
    def setUp(self):
        base.WorkflowTests.setUp(self)

    def save(self, **data):
        self.client.force_authenticate(self.admin)
        return self.client.post(URL, data, format="multipart")

    def test_admin_saves_motto_and_principal_without_a_logo(self):
        r = self.save(motto="  Strive   to excel ", principal_name="Mr. A. Otieno")
        self.assertEqual(r.status_code, 200, r.content)
        self.school.refresh_from_db()
        self.assertEqual(self.school.motto, "Strive to excel")
        self.assertEqual(self.school.principal_name, "Mr. A. Otieno")

    def test_get_returns_them(self):
        self.save(motto="Hard work", principal_name="Mrs. B")
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["motto"], "Hard work")
        self.assertEqual(r.data["principal_name"], "Mrs. B")

    def test_clearing_the_motto(self):
        self.save(motto="Hi")
        r = self.save(motto="")
        self.assertEqual(r.status_code, 200)
        self.school.refresh_from_db()
        self.assertEqual(self.school.motto, "")

    def test_too_long_motto_is_refused_and_not_saved(self):
        r = self.save(motto="x" * 201)
        self.assertEqual(r.status_code, 400)
        self.school.refresh_from_db()
        self.assertEqual(self.school.motto, "")

    def test_empty_post_still_asks_for_a_logo(self):
        r = self.save()
        self.assertEqual(r.status_code, 400)
        self.assertIn("logo", r.data["detail"].lower())

    def test_teacher_cannot_change_them(self):
        self.client.force_authenticate(self.good)
        r = self.client.post(URL, {"motto": "Mine"}, format="multipart")
        self.assertEqual(r.status_code, 403)
        self.school.refresh_from_db()
        self.assertEqual(self.school.motto, "")

    def test_report_school_block_carries_them(self):
        self.save(motto="Strive", principal_name="Mr. C")
        s = DjangoDataSource().get_school(self.school.id)
        self.assertEqual(s.motto, "Strive")
        self.assertEqual(s.principal_name, "Mr. C")
