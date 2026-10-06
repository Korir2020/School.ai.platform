from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from schools.models import (
    InvitationCode, JoinRequest, School, SchoolAdminProfile, StaffProfile,
    TeacherProfile)

PW = "Xk9-secure-pass"


class JoinFlowTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.boss = User.objects.create_user("boss", password=PW)
        SchoolAdminProfile.objects.create(user=self.boss, school=self.a)
        self.bossb = User.objects.create_user("bossb", password=PW)
        SchoolAdminProfile.objects.create(user=self.bossb, school=self.b)
        self.tu = User.objects.create_user("tu", password=PW)
        TeacherProfile.objects.create(user=self.tu, school=self.a)

    def register(self, username="jk", code="A1", role="teacher"):
        return self.client.post("/api/join/register/", {
            "username": username, "password": PW, "school_code": code,
            "role": role, "first_name": "John", "last_name": "Kiptoo"},
            format="json")

    def req(self, username):
        return JoinRequest.objects.get(user__username=username)

    def as_user(self, user, method, url, data=None):
        self.client.force_authenticate(user)
        kw = {} if method == "get" else {"format": "json"}
        r = getattr(self.client, method)(url, data, **kw)
        self.client.force_authenticate(None)
        return r

    def approve(self, username, who=None):
        url = f"/api/join-requests/{self.req(username).id}/approve/"
        return self.as_user(who or self.boss, "post", url)

    def complete(self, username, code):
        user = User.objects.get(username=username)
        return self.as_user(user, "post", "/api/join/complete/", {"code": code})

    def joined(self, username="jk", role="teacher"):
        self.register(username, role=role)
        code = self.approve(username).json()["code"]
        return code, self.complete(username, code)

    def test_register_makes_pending_request_only(self):
        r = self.register()
        self.assertEqual(r.status_code, 201)
        q = self.req("jk")
        got = (q.status, q.school_id, q.role)
        self.assertEqual(got, ("pending", self.a.id, "teacher"))
        u = User.objects.get(username="jk")
        self.assertFalse(TeacherProfile.objects.filter(user=u).exists())
        me = self.as_user(u, "get", "/api/auth/me/").json()
        self.assertEqual(me["role"], "none")

    def test_register_rejects_bad_input(self):
        self.assertEqual(self.register(code="NOPE").status_code, 404)
        self.assertEqual(self.register(role="school_admin").status_code, 400)
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.register().status_code, 400)

    def test_admin_lists_only_own_school(self):
        self.register("ja", code="A1")
        self.register("jb", code="B1")
        r = self.as_user(self.boss, "get", "/api/join-requests/").json()
        self.assertEqual([x["username"] for x in r["results"]], ["ja"])

    def test_only_own_school_admin_decides(self):
        self.register()
        self.assertEqual(self.approve("jk", self.bossb).status_code, 404)
        self.assertEqual(self.approve("jk", self.tu).status_code, 403)
        url = f"/api/join-requests/{self.req('jk').id}/approve/"
        self.assertEqual(self.client.post(url).status_code, 401)
        self.assertEqual(self.req("jk").status, "pending")

    def test_approve_issues_expiring_code(self):
        self.register()
        r = self.approve("jk").json()
        self.assertTrue(r["code"].startswith("MARIAN-"))
        self.assertEqual(len(r["code"]), 13)
        inv = InvitationCode.objects.get(code=r["code"])
        days = (inv.expires_at - timezone.now()).days
        self.assertIn(days, (6, 7))
        self.assertEqual(inv.school_id, self.a.id)
        rows = self.as_user(self.boss, "get", "/api/join-requests/").json()
        self.assertEqual(rows["results"][0]["code"], r["code"])

    def test_reject_gives_no_code(self):
        self.register()
        url = f"/api/join-requests/{self.req('jk').id}/reject/"
        self.assertEqual(self.as_user(self.boss, "post", url).status_code, 200)
        self.assertEqual(self.req("jk").status, "rejected")
        self.assertFalse(InvitationCode.objects.exists())
        self.assertEqual(self.approve("jk").status_code, 409)

    def test_full_flow_makes_teacher_without_assignments(self):
        code, r = self.joined()
        self.assertEqual(r.status_code, 200)
        u = User.objects.get(username="jk")
        self.assertEqual(TeacherProfile.objects.get(user=u).school_id, self.a.id)
        self.assertEqual(self.req("jk").status, "joined")
        self.assertIsNotNone(InvitationCode.objects.get(code=code).used_at)
        me = self.as_user(u, "get", "/api/auth/me/").json()
        self.assertEqual(me["role"], "teacher")
        self.assertEqual(self.as_user(u, "get", "/api/join-requests/").status_code, 403)

    def test_code_is_single_use(self):
        code, _ = self.joined()
        again = self.complete("jk", code)
        self.assertEqual(again.status_code, 400)
        self.assertIn("already been used", again.json()["detail"])
        self.assertEqual(TeacherProfile.objects.filter(user__username="jk").count(), 1)

    def test_wrong_and_expired_codes_fail(self):
        self.register()
        code = self.approve("jk").json()["code"]
        bad = self.complete("jk", "MARIAN-AAAAAA")
        self.assertEqual(bad.status_code, 400)
        InvitationCode.objects.filter(code=code).update(
            expires_at=timezone.now() - timedelta(days=1))
        late = self.complete("jk", code)
        self.assertIn("invalid or has expired", late.json()["detail"])
        self.assertFalse(TeacherProfile.objects.filter(user__username="jk").exists())

    def test_someone_elses_code_does_not_work(self):
        self.register("j1")
        self.register("j2", code="B1")
        c1 = self.approve("j1").json()["code"]
        self.approve("j2", self.bossb)
        r = self.complete("j2", c1)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(TeacherProfile.objects.filter(user__username="j2").exists())

    def test_unapproved_user_cannot_complete(self):
        self.register()
        r = self.complete("jk", "MARIAN-AAAAAA")
        self.assertEqual(r.status_code, 400)
        anon = self.client.post("/api/join/complete/", {"code": "x"}, format="json")
        self.assertEqual(anon.status_code, 401)

    def test_bursar_gets_staff_profile_not_teacher(self):
        self.joined("bu", role="bursar")
        u = User.objects.get(username="bu")
        self.assertEqual(StaffProfile.objects.get(user=u).role, "bursar")
        self.assertFalse(TeacherProfile.objects.filter(user=u).exists())

    def test_reapprove_reissues_code_and_joined_is_final(self):
        self.register()
        first = self.approve("jk").json()["code"]
        second = self.approve("jk").json()["code"]
        self.assertNotEqual(first, second)
        self.assertEqual(self.complete("jk", first).status_code, 400)
        self.assertEqual(self.complete("jk", second).status_code, 200)
        self.assertEqual(self.approve("jk").status_code, 409)

    def test_my_request_messages(self):
        self.register()
        u = User.objects.get(username="jk")
        r = self.as_user(u, "get", "/api/join/my-request/").json()
        self.assertEqual(r["status"], "pending")
        self.approve("jk")
        r = self.as_user(u, "get", "/api/join/my-request/").json()
        self.assertEqual(r["status"], "approved")
        self.assertIn("invitation code", r["message"])
