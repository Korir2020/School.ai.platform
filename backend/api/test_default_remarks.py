from decimal import Decimal

from rest_framework.test import APITestCase

from api import tests as base
from api.report_source import DjangoDataSource
from schools.models import Exam, ExamResult, ReportRemark


class DefaultRemarkTests(APITestCase):
    def setUp(self):
        base.WorkflowTests.setUp(self)
        self.exam = Exam.objects.create(
            school=self.school, name="E", term=self.term,
            assessment_type="end", class_level=self.stream.class_level,
        )

    def result(self, avg):
        ExamResult.objects.create(
            exam=self.exam, student=self.student, overall_average=Decimal(avg))

    def remarks(self):
        return DjangoDataSource().get_remarks(
            self.school.id, self.exam.id, self.student.id)

    def test_high_average_gets_excellent_for_both(self):
        self.result("80.00")
        self.assertEqual(self.remarks(),
                         {"class_teacher": "Excellent", "principal": "Excellent"})

    def test_bands_and_edges(self):
        for avg, word in [("75.00", "Excellent"), ("74.99", "Good"),
                          ("60.00", "Good"), ("50.00", "Fair"),
                          ("49.99", "Keep Trying"), ("12.00", "Keep Trying")]:
            ExamResult.objects.filter(exam=self.exam).delete()
            self.result(avg)
            self.assertEqual(self.remarks()["class_teacher"], word, avg)

    def test_approved_comment_wins_for_its_field_only(self):
        self.result("40.00")
        ReportRemark.objects.create(
            school=self.school, exam=self.exam, student=self.student,
            field="class_teacher", text="Works hard, can do better.")
        got = self.remarks()
        self.assertEqual(got["class_teacher"], "Works hard, can do better.")
        self.assertEqual(got["principal"], "Keep Trying")

    def test_no_published_result_means_no_default(self):
        self.assertEqual(self.remarks(), {})

    def test_deleting_the_comment_brings_back_the_default(self):
        self.result("55.00")
        r = ReportRemark.objects.create(
            school=self.school, exam=self.exam, student=self.student,
            field="principal", text="Well done.")
        self.assertEqual(self.remarks()["principal"], "Well done.")
        r.delete()
        self.assertEqual(self.remarks()["principal"], "Fair")
