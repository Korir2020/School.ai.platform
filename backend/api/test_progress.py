from datetime import date, timedelta
from datetime import date, timedelta
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Exam, ExamResult, School,
    SchoolAdminProfile, Student, TeacherProfile, Term,
)


class ProgressTests(APITestCase):
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
        self.level = ClassLevel.objects.create(curriculum=cur, name="L1", level_number=1)
        self.student = Student.objects.create(
            school=self.school, first_name="Ann", last_name="A", admission_number="A-1")
        self.admin = User.objects.create_user("admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.other = User.objects.create_user("other", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other, school=other)
        self.teacher = User.objects.create_user("teacher", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.url = f"/api/students/{self.student.id}/progress/"

    def add(self, kind, avg, scores, day):
        exam = Exam.objects.create(
            school=self.school, name=kind, term=self.term,
            class_level=self.level, assessment_type=kind,
            status="published",
            published_at=timezone.now() + timedelta(days=day))
        ExamResult.objects.create(
            exam=exam, student=self.student, overall_average=avg,
            subject_scores=scores)

    def test_sharp_drop_flagged(self):
        self.add("opener", 70, {"Math": "80", "Eng": "60"}, 0)
        self.add("end", 55, {"Math": "50", "Eng": "60"}, 1)
        self.client.force_authenticate(self.admin)
        data = self.client.get(self.url).json()
        self.assertEqual(data["trend"], "declining")
        self.assertEqual(float(data["change"]), -15.0)
        self.assertEqual(data["flags"][0]["flag"], "sharp_drop")
        self.assertEqual(data["biggest_subject_drops"][0]["subject"], "Math")

    def test_one_exam_not_enough_data(self):
        self.add("end", 55, {"Math": "50"}, 0)
        self.client.force_authenticate(self.admin)
        data = self.client.get(self.url).json()
        self.assertEqual(data["trend"], "not_enough_data")
        self.assertEqual(data["flags"], [])

    def test_other_school_admin_gets_404(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_teacher_gets_403(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
