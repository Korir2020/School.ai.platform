from datetime import date, timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Exam, ExamResult, School,
    SchoolAdminProfile, Student, TeacherProfile, Term,
)

URL = "/api/analytics/early-warning/"


def make_school(code):
    school = School.objects.create(name=code, code=code)
    year = AcademicYear.objects.create(
        school=school, name="2026",
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    term = Term.objects.create(
        academic_year=year, name="T1",
        start_date=date(2026, 1, 5), end_date=date(2026, 4, 5))
    return school, term


def add_scores(school, term, level, name, scores):
    """scores: {student: (opener_avg, end_avg)}, None = absent."""
    now = timezone.now()
    for i, kind in enumerate(["opener", "end"]):
        exam = Exam.objects.create(
            school=school, name=f"{name} {kind}", term=term,
            class_level=level, assessment_type=kind, status="published",
            published_at=now + timedelta(days=i))
        for student, avgs in scores.items():
            if avgs[i] is not None:
                ExamResult.objects.create(
                    exam=exam, student=student, overall_average=avgs[i])


class EarlyWarningTests(APITestCase):
    def setUp(self):
        a, term_a = make_school("A1")
        b, term_b = make_school("B1")
        level = ClassLevel.objects.create(
            curriculum=Curriculum.objects.create(name="C", code="C1"),
            name="L1", level_number=1)

        def stu(school, n):
            return Student.objects.create(
                school=school, first_name=n, last_name="X",
                admission_number=n)

        ann, ben = stu(a, "Ann"), stu(a, "Ben")
        cy, zed = stu(a, "Cy"), stu(b, "Zed")
        add_scores(a, term_a, level, "A", {
            ann: (70, 55), ben: (60, 58), cy: (None, 35)})
        add_scores(b, term_b, level, "B", {zed: (50, 20)})
        self.admin = User.objects.create_user("admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=a)
        self.teacher = User.objects.create_user("teacher", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=a)

    def test_flags_drop_and_low(self):
        self.client.force_authenticate(self.admin)
        data = self.client.get(URL).json()
        names = [f["name"] for f in data["results"]]
        self.assertEqual(sorted(names), ["Ann X", "Cy X"])
        self.assertEqual(data["count"], 2)
        ann = [f for f in data["results"] if f["name"] == "Ann X"][0]
        self.assertIn("Fell 15.0 points", ann["reasons"][0])

    def test_other_school_not_visible(self):
        self.client.force_authenticate(self.admin)
        text = str(self.client.get(URL).json())
        self.assertNotIn("Zed", text)

    def test_teacher_gets_403(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(URL).status_code, 401)
