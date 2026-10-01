from datetime import date

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, Performance,
    School, SchoolAdminProfile, Stream, Student, Subject, TeacherAssignment,
    TeacherProfile, Term,
)

URL = "/api/dashboard/"


class DashboardTests(APITestCase):
    def setUp(self):
        a = self.a = School.objects.create(name="A", code="A1")
        b = self.b = School.objects.create(name="B", code="B1")
        self.year = AcademicYear.objects.create(
            school=a, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="T1",
            start_date=date(2026, 1, 5), end_date=date(2026, 4, 5))
        cur = Curriculum.objects.create(name="C", code="C1")
        self.level = ClassLevel.objects.create(curriculum=cur, name="L1", level_number=1)
        self.stream = Stream.objects.create(school=a, class_level=self.level, name="East")
        self.student = Student.objects.create(
            school=a, first_name="Ann", last_name="A", admission_number="A-1")
        Enrollment.objects.create(
            student=self.student, academic_year=self.year,
            class_level=self.level, stream=self.stream)
        self.subject = Subject.objects.create(school=a, name="Math")
        self.teacher = User.objects.create_user("teacher", password="pass12345")
        tp = TeacherProfile.objects.create(user=self.teacher, school=a)
        TeacherAssignment.objects.create(
            teacher=tp, school=a, subject=self.subject, stream=self.stream)
        other_t = User.objects.create_user("other_t", password="pass12345")
        TeacherProfile.objects.create(user=other_t, school=a)
        self.admin_a = User.objects.create_user("admin_a", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_a, school=a)
        self.admin_b = User.objects.create_user("admin_b", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_b, school=b)
        self.nobody = User.objects.create_user("nobody", password="pass12345")
        self.root = User.objects.create_superuser("root", "r@x.com", "pass12345")
        common = dict(student=self.student, subject=self.subject,
                      academic_year=self.year, term=self.term)
        Performance.objects.create(
            **common, assessment_type="end", marks=50,
            status="draft", entered_by=self.teacher)
        Performance.objects.create(
            **common, assessment_type="mid", marks=60,
            status="submitted", entered_by=other_t)
        Exam.objects.create(
            school=a, name="End", term=self.term, class_level=self.level,
            assessment_type="end", status="published", published_at=timezone.now())
        Exam.objects.create(
            school=a, name="Mid", term=self.term, class_level=self.level,
            assessment_type="mid")

    def get(self, user):
        self.client.force_authenticate(user)
        return self.client.get(URL)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.get(None).status_code, 401)

    def test_user_without_profile_gets_403(self):
        self.assertEqual(self.get(self.nobody).status_code, 403)

    def test_admin_dashboard(self):
        data = self.get(self.admin_a).json()
        self.assertEqual(data["role"], "school_admin")
        self.assertEqual(data["students"], 1)
        self.assertEqual(data["active_enrollments"], 1)
        self.assertEqual(data["teachers"], 2)
        self.assertEqual(data["awaiting_approval"], 1)
        self.assertEqual(data["marks_by_status"]["draft"], 1)
        self.assertEqual(data["marks_by_status"]["submitted"], 1)
        self.assertEqual(data["exams"], {"draft": 1, "published": 1})
        self.assertEqual(data["active_term"]["name"], "T1")

    def test_other_school_admin_sees_zeros(self):
        data = self.get(self.admin_b).json()
        self.assertEqual(data["students"], 0)
        self.assertEqual(data["teachers"], 0)
        self.assertEqual(data["awaiting_approval"], 0)
        self.assertIsNone(data["active_term"])
        self.assertEqual(data["exams"], {"draft": 0, "published": 0})

    def test_teacher_sees_only_own_data(self):
        data = self.get(self.teacher).json()
        self.assertEqual(data["role"], "teacher")
        self.assertNotIn("students", data)
        self.assertNotIn("teachers", data)
        self.assertEqual(len(data["assignments"]), 1)
        self.assertEqual(data["assignments"][0]["subject"], "Math")
        self.assertEqual(data["my_marks_by_status"]["draft"], 1)
        self.assertEqual(data["my_marks_by_status"]["submitted"], 0)

    def test_superadmin_dashboard(self):
        data = self.get(self.root).json()
        self.assertEqual(data["role"], "superadmin")
        self.assertEqual(data["total_schools"], 2)
        by_name = {s["name"]: s for s in data["schools"]}
        self.assertEqual(by_name["A"]["students"], 1)
        self.assertEqual(by_name["A"]["teachers"], 2)
        self.assertEqual(by_name["B"]["students"], 0)
