from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    Enrollment, SchoolAdminProfile, Stream, Student,
)
from . import tests as base

URL = "/api/search/"


class SearchTests(APITestCase):
    def setUp(self):
        base.MarksEntryTests.setUp(self)
        level = self.stream.class_level
        w = Stream.objects.create(school=self.school, class_level=level, name="W")
        self.student2 = Student.objects.create(
            school=self.school, first_name="St", last_name="Two",
            admission_number="S-2")
        Enrollment.objects.create(
            student=self.student2, academic_year=self.year,
            class_level=level, stream=w)
        self.admin = User.objects.create_user("adm", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.root = User.objects.create_superuser("root", "r@x.com", "pass12345")

    def find(self, user, q):
        self.client.force_authenticate(user)
        r = self.client.get(URL, {"q": q})
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(URL, {"q": "st"}).status_code, 401)

    def test_short_query_returns_nothing(self):
        d = self.find(self.admin, "s")
        self.assertEqual(d["students"], [])
        self.assertEqual(d["subjects"], [])

    def test_admin_finds_by_full_name_and_admission_number(self):
        d = self.find(self.admin, "st one")
        self.assertEqual([s["id"] for s in d["students"]], [self.student.id])
        d = self.find(self.admin, "S-2")
        self.assertEqual([s["id"] for s in d["students"]], [self.student2.id])

    def test_admin_never_sees_other_school(self):
        d = self.find(self.admin, "Ot")
        self.assertEqual(d["students"], [])

    def test_teacher_sees_only_own_class_students(self):
        got = {s["id"] for s in self.find(self.good, "st")["students"]}
        self.assertEqual(got, {self.student.id})
        got = {s["id"] for s in self.find(self.admin, "st")["students"]}
        self.assertEqual(got, {self.student.id, self.student2.id})

    def test_only_admin_gets_teachers(self):
        self.assertEqual(self.find(self.good, "good")["teachers"], [])
        d = self.find(self.admin, "good")
        self.assertEqual([t["username"] for t in d["teachers"]], ["good"])

    def test_subjects_found(self):
        d = self.find(self.admin, "math")
        self.assertEqual([s["id"] for s in d["subjects"]], [self.subject.id])

    def test_only_superuser_gets_schools(self):
        self.assertEqual(self.find(self.admin, "S1")["schools"], [])
        d = self.find(self.root, "O1")
        self.assertEqual([s["code"] for s in d["schools"]], ["O1"])
