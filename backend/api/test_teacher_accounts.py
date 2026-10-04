from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import MarkAuditLog, School, SchoolAdminProfile, TeacherProfile

LOGIN = "/api/auth/login/"
NEWPW = "Str0ng-pass-91"


class TeacherAccountTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.boss = User.objects.create_user("boss", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.boss, school=self.a)
        self.other = User.objects.create_user("bossb", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other, school=self.b)
        self.tu = User.objects.create_user("ta", password="pass12345")
        self.t = TeacherProfile.objects.create(user=self.tu, school=self.a)
        self.url = f"/api/teachers/{self.t.id}/"
        self.reset = self.url + "reset-password/"

    def off(self, flag=False):
        return self.client.patch(self.url, {"is_active": flag}, format="json")

    def rp(self, pw=NEWPW):
        return self.client.post(self.reset, {"password": pw}, format="json")

    def login(self, name, pw):
        return self.client.post(LOGIN, {"username": name, "password": pw}, format="json")

    def test_anonymous_gets_401(self):
        self.assertEqual(self.off().status_code, 401)
        self.assertEqual(self.rp().status_code, 401)

    def test_teacher_gets_403(self):
        self.client.force_authenticate(self.tu)
        self.assertEqual(self.off().status_code, 403)
        self.assertEqual(self.rp().status_code, 403)

    def test_other_school_gets_404_and_nothing_changes(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.off().status_code, 404)
        self.assertEqual(self.rp().status_code, 404)
        self.tu.refresh_from_db()
        self.assertTrue(self.tu.is_active)
        self.assertTrue(self.tu.check_password("pass12345"))
        self.assertFalse(MarkAuditLog.objects.exists())

    def test_is_active_must_be_a_real_boolean(self):
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.off("false").status_code, 400)
        self.assertEqual(self.off(None).status_code, 400)
        self.tu.refresh_from_db()
        self.assertTrue(self.tu.is_active)

    def test_admin_deactivates_and_reactivates(self):
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.off(False).status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.login("ta", "pass12345").status_code, 401)
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.off(True).status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.login("ta", "pass12345").status_code, 200)
        rows = MarkAuditLog.objects.order_by("id")
        acts = list(rows.values_list("action", flat=True))
        self.assertEqual(acts, ["teacher_deactivated", "teacher_activated"])

    def test_deputy_can_deactivate_and_reset(self):
        dep = User.objects.create_user("dep", password="pass12345")
        SchoolAdminProfile.objects.create(user=dep, school=self.a, is_deputy=True)
        self.client.force_authenticate(dep)
        self.assertEqual(self.off().status_code, 200)
        self.assertEqual(self.rp().status_code, 200)

    def test_reset_password_logs_out_old_sessions(self):
        old = self.login("ta", "pass12345").json()["refresh"]
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.rp().status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.login("ta", "pass12345").status_code, 401)
        self.assertEqual(self.login("ta", NEWPW).status_code, 200)
        r = self.client.post("/api/auth/refresh/", {"refresh": old}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_weak_password_rejected_and_not_logged(self):
        self.client.force_authenticate(self.boss)
        self.assertEqual(self.rp("123").status_code, 400)
        self.assertEqual(self.rp("").status_code, 400)
        self.tu.refresh_from_db()
        self.assertTrue(self.tu.check_password("pass12345"))
        self.assertFalse(MarkAuditLog.objects.exists())

    def test_audit_entry_never_holds_the_password(self):
        self.client.force_authenticate(self.boss)
        self.rp()
        log = MarkAuditLog.objects.get(action="teacher_password_reset")
        self.assertEqual(log.school_id, self.a.id)
        self.assertEqual(log.user_id, self.boss.id)
        self.assertEqual(log.details, {"teacher": "ta"})
