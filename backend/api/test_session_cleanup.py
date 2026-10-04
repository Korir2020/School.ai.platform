from django.contrib.auth.models import User
from rest_framework.test import APITestCase

URL = "/api/auth/change-password/"
LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/refresh/"
NEWPW = "Str0ng-pass-91"


class OtherSessionsTests(APITestCase):
    def setUp(self):
        self.u = User.objects.create_user("su", password="pass12345")
        self.v = User.objects.create_user("sv", password="pass12345")

    def token(self, name):
        body = {"username": name, "password": "pass12345"}
        return self.client.post(LOGIN, body, format="json").json()["refresh"]

    def change(self, refresh=None):
        self.client.force_authenticate(self.u)
        body = {"old_password": "pass12345", "new_password": NEWPW}
        if refresh is not None:
            body["refresh"] = refresh
        code = self.client.post(URL, body, format="json").status_code
        self.client.force_authenticate(None)
        return code

    def renew(self, refresh):
        body = {"refresh": refresh}
        return self.client.post(REFRESH, body, format="json").status_code

    def test_other_devices_signed_out_this_one_kept(self):
        mine, other = self.token("su"), self.token("su")
        self.assertEqual(self.change(mine), 200)
        self.assertEqual(self.renew(other), 401)
        self.assertEqual(self.renew(mine), 200)

    def test_no_token_sent_signs_out_everywhere(self):
        a, b = self.token("su"), self.token("su")
        self.client.cookies.clear()
        self.assertEqual(self.change(), 200)
        self.assertEqual(self.renew(a), 401)
        self.assertEqual(self.renew(b), 401)

    def test_someone_elses_token_is_not_kept(self):
        mine, theirs = self.token("su"), self.token("sv")
        self.assertEqual(self.change(theirs), 200)
        self.assertEqual(self.renew(mine), 401)
        self.assertEqual(self.renew(theirs), 200)

    def test_garbage_token_still_changes_password(self):
        mine = self.token("su")
        self.assertEqual(self.change("not-a-token"), 200)
        self.assertEqual(self.renew(mine), 401)
        self.u.refresh_from_db()
        self.assertTrue(self.u.check_password(NEWPW))
