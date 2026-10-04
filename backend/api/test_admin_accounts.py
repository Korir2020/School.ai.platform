from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from schools.models import MarkAuditLog, School, SchoolAdminProfile, TeacherProfile

LIST = "/api/admin-accounts/"
NEW = "Str0ng-pass-91"


class AdminAccountTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.root = User.objects.create_superuser("root", "r@x.com", "pass12345")
        self.boss = self.admin("boss", self.a)
        self.boss2 = self.admin("boss2", self.a)
        self.dep = self.admin("dep", self.a, True)
        self.depb = self.admin("depb", self.b, True)
        self.teacher = User.objects.create_user("ta", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.a)

    def admin(self, name, school, deputy=False):
        u = User.objects.create_user(name, password="pass12345")
        return SchoolAdminProfile.objects.create(user=u, school=school, is_deputy=deputy)

    def reset(self, user, profile, pw=NEW):
        self.client.force_authenticate(user)
        return self.client.post(f"{LIST}{profile.id}/reset-password/", {"password": pw}, format="json")

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(LIST).status_code, 401)
        self.assertEqual(self.client.post(f"{LIST}{self.dep.id}/reset-password/").status_code, 401)

    def test_list_is_superuser_only(self):
        for u in (self.boss.user, self.teacher):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get(LIST).status_code, 403)
        self.client.force_authenticate(self.root)
        r = self.client.get(LIST).json()
        self.assertEqual(len(r["results"]), 4)

    def test_superuser_resets_school_admin(self):
        self.assertEqual(self.reset(self.root, self.boss).status_code, 200)
        self.boss.user.refresh_from_db()
        self.assertTrue(self.boss.user.check_password(NEW))
        self.assertTrue(MarkAuditLog.objects.filter(action="admin_password_reset", school=self.a).exists())

    def test_admin_resets_own_deputy_and_signs_them_out(self):
        RefreshToken.for_user(self.dep.user)
        self.assertEqual(self.reset(self.boss.user, self.dep).status_code, 200)
        self.dep.user.refresh_from_db()
        self.assertTrue(self.dep.user.check_password(NEW))
        self.assertEqual(BlacklistedToken.objects.filter(token__user=self.dep.user).count(), 1)

    def test_scope_and_roles(self):
        self.assertEqual(self.reset(self.boss.user, self.depb).status_code, 404)
        self.assertEqual(self.reset(self.boss.user, self.boss2).status_code, 403)
        self.assertEqual(self.reset(self.dep.user, self.boss).status_code, 403)
        self.assertEqual(self.reset(self.teacher, self.dep).status_code, 403)

    def test_weak_password_rejected(self):
        self.assertEqual(self.reset(self.boss.user, self.dep, "123").status_code, 400)
        self.dep.user.refresh_from_db()
        self.assertTrue(self.dep.user.check_password("pass12345"))
