from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from schools.models import MarkAuditLog
from . import tests as base

URL = "/api/notifications/"
EP = base.ExamPublishTests


class NotificationTests(APITestCase):
    def setUp(self):
        EP.setUp(self)
        self.s2 = EP.add_student(self, "S-2")

    def get(self, user):
        self.client.force_authenticate(user)
        return self.client.get(URL)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_teacher_gets_403(self):
        self.assertEqual(self.get(self.good).status_code, 403)

    def test_empty_when_nothing_to_report(self):
        d = self.get(self.admin).json()
        self.assertEqual((d["count"], d["results"]), (0, []))

    def test_submitted_marks_are_reported(self):
        EP.mark(self, self.student, 1, 60, status="submitted")
        EP.mark(self, self.s2, 1, 70, status="submitted")
        item = self.get(self.admin).json()["results"][0]
        self.assertEqual(item["kind"], "marks_awaiting_approval")
        self.assertEqual(item["count"], 2)

    def test_not_ranked_after_publish(self):
        EP.mark(self, self.student, 1, 70)
        self.assertEqual(EP.publish(self, self.admin).status_code, 200)
        item = self.get(self.admin).json()["results"][0]
        self.assertEqual(item["kind"], "students_not_ranked")
        self.assertEqual(item["admission_numbers"], ["S-2"])
        self.assertEqual(item["exam"], "E")

    def test_old_publish_is_not_reported(self):
        EP.mark(self, self.student, 1, 70)
        EP.publish(self, self.admin)
        old = timezone.now() - timedelta(days=31)
        MarkAuditLog.objects.filter(action="publish").update(timestamp=old)
        self.assertEqual(self.get(self.admin).json()["count"], 0)
