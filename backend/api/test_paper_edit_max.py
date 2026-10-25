from decimal import Decimal

from rest_framework.test import APITestCase

from api import tests as base
from schools.models import Exam, Performance, SubjectPaper


class PaperEditMaxTests(APITestCase):
    def setUp(self):
        base.WorkflowTests.setUp(self)
        self.paper = SubjectPaper.objects.create(
            subject=self.subject, paper_number=1, weight=Decimal("100"), max_marks=Decimal("100"))
        self.url = f"/api/subject-papers/{self.paper.id}/"

    def patch(self, user, data):
        self.client.force_authenticate(user)
        return self.client.patch(self.url, data, format="json")

    def mark(self, marks):
        return Performance.objects.create(
            student=self.student, subject=self.subject, academic_year=self.year,
            term=self.term, assessment_type="end", paper_number=1,
            marks=Decimal(str(marks)), status="approved")

    def test_admin_sets_max_marks(self):
        r = self.patch(self.admin, {"max_marks": "80"})
        self.assertEqual(r.status_code, 200, r.content)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.max_marks, Decimal("80"))

    def test_weight_only_edit_still_works(self):
        r = self.patch(self.admin, {"weight": "60"})
        self.assertEqual(r.status_code, 200, r.content)

    def test_max_outside_1_to_100_refused(self):
        self.assertEqual(self.patch(self.admin, {"max_marks": "0"}).status_code, 400)
        self.assertEqual(self.patch(self.admin, {"max_marks": "101"}).status_code, 400)

    def test_max_cannot_go_below_existing_marks(self):
        self.mark(70)
        self.assertEqual(self.patch(self.admin, {"max_marks": "60"}).status_code, 400)
        self.assertEqual(self.patch(self.admin, {"max_marks": "70"}).status_code, 200)

    def test_locked_after_published_exam(self):
        self.mark(50)
        Exam.objects.create(
            school=self.school, name="E", term=self.term, assessment_type="end",
            class_level=self.stream.class_level, status="published")
        self.assertEqual(self.patch(self.admin, {"max_marks": "80"}).status_code, 409)

    def test_teacher_cannot_edit(self):
        self.assertEqual(self.patch(self.good, {"max_marks": "80"}).status_code, 403)

    def test_empty_edit_refused(self):
        self.assertEqual(self.patch(self.admin, {}).status_code, 400)
