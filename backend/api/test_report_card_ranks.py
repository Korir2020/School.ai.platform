from datetime import date

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from schools.models import (
    Enrollment, Stream, Subject, TeacherAssignment,
    AcademicYear, ClassLevel, Curriculum, Exam, ExamResult, School,
    SchoolAdminProfile, Student, TeacherProfile, Term,
)


class ReportCardRankTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="A", code="A1")
        other = School.objects.create(name="B", code="B1")
        year = AcademicYear.objects.create(
            school=self.school, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=year, name="T1",
            start_date=date(2026, 1, 5), end_date=date(2026, 4, 5))
        cur = Curriculum.objects.create(name="C", code="C1")
        level = ClassLevel.objects.create(curriculum=cur, name="L1", level_number=1)
        self.student = Student.objects.create(
            school=self.school, first_name="Ann", last_name="A", admission_number="A-1")
        self.pub = Exam.objects.create(
            school=self.school, name="End T1", term=self.term, class_level=level,
            assessment_type="end", status="published", published_at=timezone.now())
        self.draft = Exam.objects.create(
            school=self.school, name="Mid T1", term=self.term, class_level=level,
            assessment_type="mid", status="draft")
        ExamResult.objects.create(
            exam=self.pub, student=self.student, overall_average="72.50",
            stream_rank=2, class_rank=5)
        ExamResult.objects.create(
            exam=self.draft, student=self.student, overall_average="10.00",
            stream_rank=9, class_rank=9)
        self.admin = User.objects.create_user("admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher = User.objects.create_user("teacher", password="pass12345")
        tp = TeacherProfile.objects.create(user=self.teacher, school=self.school)
        stream = Stream.objects.create(school=self.school, class_level=level, name="E")
        Enrollment.objects.create(
            student=self.student, academic_year=year, class_level=level, stream=stream)
        subj = Subject.objects.create(school=self.school, name="M", code="M")
        TeacherAssignment.objects.create(
            teacher=tp, school=self.school, subject=subj, stream=stream)
        self.other_admin = User.objects.create_user("other", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=other)
        self.url = f"/api/report-card/{self.student.id}/{self.term.id}/"

    def test_admin_sees_only_published_ranks(self):
        self.client.force_authenticate(self.admin)
        data = self.client.get(self.url).json()
        results = data["published_results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["exam"], "End T1")
        self.assertEqual(results[0]["class_rank"], 5)
        self.assertEqual(results[0]["overall_average"], "72.50")

    def test_teacher_sees_no_ranks(self):
        self.client.force_authenticate(self.teacher)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("published_results", r.json())

    def test_other_school_admin_gets_404(self):
        self.client.force_authenticate(self.other_admin)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
