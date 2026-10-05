"""Report card shows did-not-sit for a published exam with no result."""
from django.utils import timezone
from rest_framework.test import APITestCase

from . import test_report_card_ranks as base
from schools.models import ClassLevel, Exam, ExamResult


class DidNotSitTests(APITestCase):
    def setUp(self):
        base.ReportCardRankTests.setUp(self)
        self.level = self.pub.class_level

    def card(self, user):
        self.client.force_authenticate(user)
        url = f"/api/report-card/{self.student.id}/{self.term.id}/"
        return self.client.get(url).json()

    def drop_result(self):
        ExamResult.objects.filter(
            student=self.student, exam=self.pub).delete()

    def test_with_result_list_is_empty(self):
        self.assertEqual(self.card(self.admin)["did_not_sit"], [])

    def test_without_result_is_listed(self):
        self.drop_result()
        got = self.card(self.admin)["did_not_sit"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["exam"], "End T1")
        self.assertIn("Did not sit", got[0]["note"])

    def test_draft_exam_not_listed(self):
        ExamResult.objects.all().delete()
        names = [d["exam"] for d in self.card(self.admin)["did_not_sit"]]
        self.assertEqual(names, ["End T1"])

    def test_other_class_level_not_listed(self):
        self.drop_result()
        other = ClassLevel.objects.create(
            curriculum=self.level.curriculum, name="L2", level_number=2)
        Exam.objects.create(
            school=self.school, name="End L2", term=self.term,
            class_level=other, assessment_type="end",
            status="published", published_at=timezone.now())
        names = [d["exam"] for d in self.card(self.admin)["did_not_sit"]]
        self.assertEqual(names, ["End T1"])

    def test_teacher_sees_note_never_ranks(self):
        self.drop_result()
        data = self.card(self.teacher)
        self.assertEqual(len(data["did_not_sit"]), 1)
        self.assertNotIn("published_results", data)
