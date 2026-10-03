from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import School, SchoolAdminProfile, TeacherProfile

URL = "/api/deputies/"
LOGIN = "/api/auth/login/"
BODY = {"username": "dep1", "password": "Str0ng-pass-91", "first_name": "Dan", "last_name": "Deputy"}


class DeputyTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.boss = User.objects.create_user("boss", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.boss, school=self.a)
        self.other = User.objects.create_user("bossb", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other, school=self.b)
        self.teacher = User.objects.create_user("ta", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.a)

    def appoint(self):
        self.client.force_authenticate(self.boss)
        r = self.client.post(URL, BODY, format="json")
        self.client.force_authenticate(None)
        return r

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_teacher_cannot_manage(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.post(URL, BODY, format="json").status_code, 403)

    def test_admin_appoints_deputy_in_own_school(self):
        self.assertEqual(self.appoint().status_code, 201)
        p = SchoolAdminProfile.objects.get(user__username="dep1")
        self.assertTrue(p.is_deputy)
        self.assertEqual(p.school_id, self.a.id)

    def test_weak_password_and_duplicate_rejected(self):
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.client.post(URL, {**BODY, "password": "123"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(URL, {**BODY, "username": "ta"}, format="json").status_code, 400)

    def test_deputy_cannot_manage_deputies(self):
        self.appoint()
        self.client.force_authenticate(User.objects.get(username="dep1"))
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.post(URL, {**BODY, "username": "dep2"}, format="json").status_code, 403)

    def test_deputy_has_admin_powers(self):
        self.appoint()
        self.client.force_authenticate(User.objects.get(username="dep1"))
        self.assertEqual(self.client.get("/api/dashboard/").json()["role"], "school_admin")
        me = self.client.get("/api/auth/me/").json()
        self.assertTrue(me["is_deputy"])
        body = {"username": "t_new", "password": "Str0ng-pass-91"}
        self.assertEqual(self.client.post("/api/teachers/", body, format="json").status_code, 201)

    def test_list_only_own_school(self):
        self.appoint()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(URL).json()["results"], [])
        self.client.force_authenticate(self.boss)
        self.assertEqual(len(self.client.get(URL).json()["results"]), 1)

    def test_other_school_cannot_remove(self):
        pid = self.appoint().json()["id"]
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(URL + str(pid) + "/").status_code, 404)

    def test_removed_deputy_cannot_log_in(self):
        pid = self.appoint().json()["id"]
        ok = {"username": "dep1", "password": "Str0ng-pass-91"}
        self.assertEqual(self.client.post(LOGIN, ok).status_code, 200)
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.client.delete(URL + str(pid) + "/").status_code, 204)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(LOGIN, ok).status_code, 401)
        self.assertFalse(SchoolAdminProfile.objects.filter(user__username="dep1").exists())
