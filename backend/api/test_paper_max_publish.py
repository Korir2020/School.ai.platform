from decimal import Decimal

from rest_framework.test import APITestCase

from api import tests as base
from schools.models import Exam, ExamResult, Performance, SubjectPaper


class PaperMaxPublishTests(APITestCase):
    def setUp(self):
        base.WorkflowTests.setUp(self)
        self.exam = Exam.objects.create(
            school=self.school, name="E", term=self.term,
            assessment_type="end", class_level=self.stream.class_level,
        )

    def paper(self, number, weight, max_marks="100"):
        return SubjectPaper.objects.create(
            subject=self.subject, paper_number=number,
            weight=Decimal(weight), max_marks=Decimal(max_marks))

    def mark(self, paper, marks):
        return Performance.objects.create(
            student=self.student, subject=self.subject, academic_year=self.year,
            term=self.term, assessment_type="end", paper_number=paper,
            marks=Decimal(str(marks)), status="approved")

    def publish_and_average(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post(f"/api/exams/{self.exam.id}/publish/")
        self.assertEqual(r.status_code, 200, r.content)
        return str(ExamResult.objects.get(exam=self.exam, student=self.student).overall_average)

    def test_two_papers_out_of_90(self):
        self.paper(1, "50", "90"); self.paper(2, "50", "90")
        self.mark(1, 60); self.mark(2, 55)
        self.assertEqual(self.publish_and_average(), "63.89")

    def test_sciences_80_80_40_weights_40_40_20(self):
        self.paper(1, "40", "80"); self.paper(2, "40", "80"); self.paper(3, "20", "40")
        self.mark(1, 60); self.mark(2, 55); self.mark(3, 30)
        self.assertEqual(self.publish_and_average(), "72.50")

    def test_unequal_weights_use_the_weights(self):
        self.paper(1, "60", "90"); self.paper(2, "40", "90")
        self.mark(1, 60); self.mark(2, 55)
        self.assertEqual(self.publish_and_average(), "64.44")

    def test_papers_out_of_100_unchanged(self):
        self.paper(1, "60"); self.paper(2, "40")
        self.mark(1, 80); self.mark(2, 50)
        self.assertEqual(self.publish_and_average(), "68.00")

    def test_different_maximums_in_one_subject(self):
        self.paper(1, "50", "80"); self.paper(2, "50", "100")
        self.mark(1, 60); self.mark(2, 60)
        self.assertEqual(self.publish_and_average(), "67.50")
