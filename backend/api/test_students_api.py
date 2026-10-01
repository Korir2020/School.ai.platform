from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import School, Student, TeacherProfile, SchoolAdminProfile

URL = "/api/students/"
BODY = {"first_name": "New", "last_name": "Kid", "admission_number": "N-1"}


class StudentCreateTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.admin_a = User.objects.create_user("admin_a", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_a, school=self.a)
        self.teacher_a = User.objects.create_user("teacher_a", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher_a, school=self.a)
        self.nobody = User.objects.create_user("nobody", password="pass12345")
        self.root = User.objects.create_superuser("root", "r@x.com", "pass12345")

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.post(URL, BODY).status_code, 401)

    def test_teacher_gets_403(self):
        self.client.force_authenticate(self.teacher_a)
        self.assertEqual(self.client.post(URL, BODY).status_code, 403)
        self.assertEqual(Student.objects.count(), 0)

    def test_user_without_profile_gets_403(self):
        self.client.force_authenticate(self.nobody)
        self.assertEqual(self.client.post(URL, BODY).status_code, 403)

    def test_admin_creates_in_own_school(self):
        self.client.force_authenticate(self.admin_a)
        r = self.client.post(URL, BODY, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Student.objects.get().school_id, self.a.id)

    def test_admin_cannot_target_other_school(self):
        self.client.force_authenticate(self.admin_a)
        r = self.client.post(URL, {**BODY, "school": self.b.id}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Student.objects.get().school_id, self.a.id)

    def test_superuser_must_choose_school(self):
        self.client.force_authenticate(self.root)
        self.assertEqual(self.client.post(URL, BODY, format="json").status_code, 400)
        r = self.client.post(URL, {**BODY, "school": self.b.id}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Student.objects.get().school_id, self.b.id)

    def test_missing_fields_gets_400(self):
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.post(URL, {}, format="json").status_code, 400)
