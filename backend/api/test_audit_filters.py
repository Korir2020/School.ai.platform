from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import MarkAuditLog, School, SchoolAdminProfile

URL = "/api/audit-logs/"


class AuditFilterTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.boss = User.objects.create_user("boss", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.boss, school=self.a)
        self.other = User.objects.create_user("other", password="pass12345")
        MarkAuditLog.objects.create(school=self.a, user=self.boss, action="publish")
        MarkAuditLog.objects.create(school=self.a, user=self.other, action="created")
        MarkAuditLog.objects.create(school=self.b, user=self.other, action="publish")
        self.client.force_authenticate(self.boss)

    def get(self, query=""):
        return self.client.get(URL + query).json()

    def test_no_filter_returns_own_school_only(self):
        self.assertEqual(len(self.get()), 2)

    def test_filter_by_action_and_user(self):
        self.assertEqual([r["action"] for r in self.get("?action=publish")], ["publish"])
        self.assertEqual([r["user"] for r in self.get("?user=other")], ["other"])

    def test_filter_by_dates(self):
        self.assertEqual(len(self.get("?date_from=2000-01-01")), 2)
        self.assertEqual(len(self.get("?date_from=2999-01-01")), 0)
        self.assertEqual(len(self.get("?date_to=2000-01-01")), 0)
        self.assertEqual(len(self.get("?date_from=not-a-date")), 2)
