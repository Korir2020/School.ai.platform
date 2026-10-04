from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    Enrollment, Performance, SchoolAdminProfile, Stream, Student,
    TeacherAssignment, TeacherProfile,
)
from .tests import MarksEntryTests


class TeacherScopeTests(APITestCase):
    def setUp(self):
        MarksEntryTests.setUp(self)
        level = self.stream.class_level
        w = Stream.objects.create(school=self.school, class_level=level, name="W")
        self.student2 = Student.objects.create(
            school=self.school, first_name="St", last_name="Two",
            admission_number="S-2",
        )
        Enrollment.objects.create(
            student=self.student2, academic_year=self.year,
            class_level=level, stream=w,
        )
        self.t2 = User.objects.create_user("t2", password="pass12345")
        tp = TeacherProfile.objects.create(user=self.t2, school=self.school)
        TeacherAssignment.objects.create(
            teacher=tp, school=self.school, subject=self.subject, stream=w,
        )
        for st in (self.student, self.student2):
            Performance.objects.create(
                student=st, subject=self.subject, academic_year=self.year,
                term=self.term, assessment_type="end", paper_number=1,
                marks=70, status="approved",
            )

    def get(self, user, url):
        self.client.force_authenticate(user)
        return self.client.get(url)

    def ids(self, user, url, key="id"):
        r = self.get(user, url)
        self.assertEqual(r.status_code, 200)
        return {x[key] for x in r.json()["results"]}

    def test_lists_only_own_classes(self):
        s1, s2 = self.student.id, self.student2.id
        self.assertEqual(self.ids(self.good, "/api/students/"), {s1})
        self.assertEqual(self.ids(self.t2, "/api/students/"), {s2})
        self.assertEqual(self.ids(self.good, "/api/enrollments/", "student"), {s1})
        self.assertEqual(self.ids(self.good, "/api/performance/", "student"), {s1})
        self.assertEqual(self.ids(self.t2, "/api/performance/", "student"), {s2})

    def test_teacher_without_assignments_sees_nothing(self):
        self.assertEqual(self.ids(self.bad, "/api/students/"), set())
        self.assertEqual(self.ids(self.bad, "/api/performance/"), set())

    def test_details_and_report_card_hidden(self):
        t = self.term.id
        own = f"/api/students/{self.student.id}/"
        self.assertEqual(self.get(self.good, own).status_code, 200)
        hidden = (
            f"/api/students/{self.student2.id}/",
            f"/api/students/{self.other_student.id}/",
            f"/api/report-card/{self.student2.id}/{t}/",
        )
        for url in hidden:
            self.assertEqual(self.get(self.good, url).status_code, 404, url)
        card = f"/api/report-card/{self.student.id}/{t}/"
        self.assertEqual(self.get(self.good, card).status_code, 200)

    def test_assignments_only_own(self):
        r = self.get(self.good, "/api/teacher-assignments/")
        self.assertEqual(r.json()["count"], 1)

    def test_admin_sees_whole_school(self):
        admin = User.objects.create_user("adm9", password="pass12345")
        SchoolAdminProfile.objects.create(user=admin, school=self.school)
        both = {self.student.id, self.student2.id}
        self.assertEqual(self.ids(admin, "/api/students/"), both)
