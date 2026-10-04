from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

LOGIN, REFRESH = "/api/auth/login/", "/api/auth/refresh/"


class CookieTests(APITestCase):
    def setUp(self):
        User.objects.create_user("tom", password="pass-12345")
        self.r = self.client.post(LOGIN, {"username": "tom", "password": "pass-12345"})

    def test_login_sets_cookie_flags(self):
        c = self.r.cookies["marian_rt"]
        self.assertTrue(c["httponly"])
        self.assertEqual(c["samesite"], "Lax")
        self.assertEqual(c["path"], "/api/auth/")
        self.assertEqual(c.value, self.r.json()["refresh"])

    def test_refresh_from_cookie_only(self):
        r = self.client.post(REFRESH, {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.json())
        self.assertNotEqual(r.cookies["marian_rt"].value, self.r.json()["refresh"])

    def test_refresh_from_body_still_works(self):
        self.client.cookies.clear()
        tok = self.r.json()["refresh"]
        r = self.client.post(REFRESH, {"refresh": tok}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_nothing_sent_is_400(self):
        self.client.cookies.clear()
        r = self.client.post(REFRESH, {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_rotated_token_is_rejected(self):
        old = self.r.json()["refresh"]
        self.client.post(REFRESH, {}, format="json")
        self.client.cookies.clear()
        r = self.client.post(REFRESH, {"refresh": old}, format="json")
        self.assertEqual(r.status_code, 401)

    @override_settings(DEBUG=False)
    def test_secure_flag_when_not_debug(self):
        self.client.cookies.clear()
        r = self.client.post(LOGIN, {"username": "tom", "password": "pass-12345"})
        self.assertTrue(r.cookies["marian_rt"]["secure"])

    def test_bad_login_sets_no_cookie(self):
        r = self.client.post(LOGIN, {"username": "tom", "password": "x"})
        self.assertNotIn("marian_rt", r.cookies)
