from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import School, SchoolAdminProfile, TeacherProfile

URL = "/api/teachers/"
BODY = {"username": "t_new", "password": "Str0ng-pass-91", "first_name": "Jane", "last_name": "Doe"}


class TeacherApiTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.admin = User.objects.create_user("adm", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.a)
        other = User.objects.create_user("tb", password="pass12345")
        TeacherProfile.objects.create(user=other, school=self.b)
        self.teacher = User.objects.create_user("ta", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.a)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_teacher_cannot_manage(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.post(URL, BODY, format="json").status_code, 403)

    def test_admin_creates_teacher_in_own_school(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(URL, BODY, format="json").status_code, 201)
        self.assertEqual(TeacherProfile.objects.get(user__username="t_new").school_id, self.a.id)

    def test_list_only_own_school(self):
        self.client.force_authenticate(self.admin)
        names = [t["username"] for t in self.client.get(URL).json()["results"]]
        self.assertEqual(names, ["ta"])

    def test_duplicate_and_weak_password_rejected(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(URL, {**BODY, "username": "ta"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(URL, {**BODY, "password": "123"}, format="json").status_code, 400)
