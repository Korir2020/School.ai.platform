from datetime import date

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, Performance, School, SchoolAdminProfile, Student, Subject,
    TeacherProfile, Term,
)

URL = "/api/approvals/summary/"


class ApprovalsSummaryTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.admin = User.objects.create_user("boss", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.a)
        self.teacher = User.objects.create_user("ta", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.a)
        self.root = User.objects.create_superuser("root", "r@x.com", "pass12345")
        self.math = self.make(self.a, "Math", [0, 100, 50, 50])
        self.eng = self.make(self.a, "Eng", [60, 62], extra=("draft", 5))
        self.make(self.b, "Other", [0, 100])

    def make(self, school, name, marks, extra=None):
        year, _ = AcademicYear.objects.get_or_create(
            school=school, name="2026",
            defaults=dict(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
        term, _ = Term.objects.get_or_create(
            academic_year=year, name="T1",
            defaults=dict(start_date=date(2026, 1, 5), end_date=date(2026, 4, 5)))
        subject = Subject.objects.create(school=school, name=name)
        rows = [("submitted", m) for m in marks] + ([extra] if extra else [])
        for i, (status, m) in enumerate(rows):
            s = Student.objects.create(school=school, first_name="S", last_name=name,
                                       admission_number=f"{name}-{i}")
            Performance.objects.create(student=s, subject=subject, academic_year=year,
                                       term=term, marks=m, status=status)
        return subject

    def get(self, user):
        self.client.force_authenticate(user)
        return self.client.get(URL)

    def test_anonymous_401_teacher_403_superuser_403(self):
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.assertEqual(self.get(self.teacher).status_code, 403)
        self.assertEqual(self.get(self.root).status_code, 403)

    def test_groups_counts_and_flags(self):
        d = self.get(self.admin).json()
        self.assertEqual(d["total_submitted"], 6)
        self.assertEqual(d["flagged_groups"], 1)
        by = {r["subject"]: r for r in d["results"]}
        self.assertEqual(set(by), {"Math", "Eng"})
        self.assertEqual(by["Math"]["flags"], ["has_zero", "has_hundred", "wide_spread"])
        self.assertEqual(by["Math"]["average"], 50.0)
        self.assertEqual(by["Eng"]["flags"], [])
        self.assertEqual(by["Eng"]["count"], 2)
