from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    JoinRequest, Notification, School, SchoolAdminProfile)

PW = "Xk9-secure-pass"
URL = "/api/notifications/"


class StoredNotificationTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.boss = self.admin(self.a, "boss")
        self.dep = self.admin(self.a, "dep", True)
        self.bossb = self.admin(self.b, "bossb")

    def admin(self, school, name, deputy=False):
        u = User.objects.create_user(name, password=PW)
        SchoolAdminProfile.objects.create(
            user=u, school=school, is_deputy=deputy)
        return u

    def call(self, user, method, url, data=None):
        self.client.force_authenticate(user)
        kw = {} if method == "get" else {"format": "json"}
        r = getattr(self.client, method)(url, data, **kw)
        self.client.force_authenticate(None)
        return r

    def register(self, username="jk", code="A1"):
        return self.client.post("/api/join/register/", {
            "username": username, "password": PW, "school_code": code,
            "role": "teacher"}, format="json")

    def test_request_notifies_own_school_admins_only(self):
        self.register()
        for u in (self.boss, self.dep):
            rows = Notification.objects.filter(recipient=u)
            self.assertEqual([n.kind for n in rows], ["join_requested"])
        left = Notification.objects.filter(recipient=self.bossb)
        self.assertFalse(left.exists())

    def test_other_school_never_sees_them(self):
        self.register()
        r = self.call(self.bossb, "get", URL).json()
        self.assertEqual(r["results"], [])
        r = self.call(self.boss, "get", URL).json()
        self.assertEqual(r["unread"], 1)

    def test_decision_notifies_the_staff_member(self):
        self.register()
        jid = JoinRequest.objects.get().id
        self.call(self.boss, "post", f"/api/join-requests/{jid}/approve/")
        u = User.objects.get(username="jk")
        r = self.call(u, "get", URL).json()
        self.assertEqual([x["kind"] for x in r["results"]], ["join_approved"])
        self.assertNotIn("MARIAN-", str(r))

    def test_completion_notifies_admins(self):
        self.register()
        jid = JoinRequest.objects.get().id
        code = self.call(self.boss, "post",
                         f"/api/join-requests/{jid}/approve/").json()["code"]
        u = User.objects.get(username="jk")
        self.call(u, "post", "/api/join/complete/", {"code": code})
        rows = Notification.objects.filter(recipient=self.dep)
        kinds = sorted(n.kind for n in rows)
        self.assertEqual(kinds, ["join_completed", "join_requested"])

    def test_mark_read_own_only(self):
        self.register()
        n = Notification.objects.get(recipient=self.boss)
        url = f"/api/notifications/{n.id}/read/"
        self.assertEqual(self.call(self.dep, "post", url).status_code, 404)
        self.assertEqual(self.call(self.boss, "post", url).status_code, 200)
        r = self.call(self.boss, "get", URL).json()
        self.assertEqual(r["unread"], 0)

    def test_read_all_and_anonymous(self):
        self.register()
        url = "/api/notifications/read-all/"
        self.assertEqual(self.client.post(url).status_code, 401)
        r = self.call(self.boss, "post", url).json()
        self.assertEqual(r["marked"], 1)
        r = self.call(self.dep, "get", URL).json()
        self.assertEqual(r["unread"], 1)
