from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase

LOGIN, REFRESH = "/api/auth/login/", "/api/auth/refresh/"
LOGOUT, PW = "/api/auth/logout/", "/api/auth/change-password/"
BAD = {"HTTP_ORIGIN": "https://evil.example"}
CRED = {"username": "tom", "password": "pass-12345"}


class CookieSessionTests(APITestCase):
    def setUp(self):
        User.objects.create_user("tom", password="pass-12345")
        self.r = self.client.post(LOGIN, CRED)

    def post(self, url, data=None, **extra):
        return self.client.post(url, data or {}, format="json", **extra)

    def test_foreign_origin_refresh_is_403(self):
        self.assertEqual(self.post(REFRESH, **BAD).status_code, 403)

    def test_own_origin_refresh_is_ok(self):
        r = self.post(REFRESH, HTTP_ORIGIN="http://testserver")
        self.assertEqual(r.status_code, 200)

    def test_logout_uses_and_clears_cookie(self):
        old = self.r.json()["refresh"]
        r = self.post(LOGOUT)
        self.assertEqual(r.status_code, 205)
        self.assertEqual(r.cookies["marian_rt"].value, "")
        self.assertEqual(self.post(REFRESH, {"refresh": old}).status_code, 401)

    def test_foreign_origin_logout_is_403_and_keeps_token(self):
        self.assertEqual(self.post(LOGOUT, **BAD).status_code, 403)
        self.assertEqual(self.post(REFRESH).status_code, 200)

    def test_change_password_keeps_this_device_only(self):
        other = APIClient().post(LOGIN, CRED).json()["refresh"]
        tok = "Bearer " + self.r.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=tok)
        body = {"old_password": "pass-12345", "new_password": "Brand-new-9xZ!"}
        self.assertEqual(self.post(PW, body).status_code, 200)
        self.client.credentials()
        self.assertEqual(self.post(REFRESH).status_code, 200)
        r = APIClient().post(REFRESH, {"refresh": other}, format="json")
        self.assertEqual(r.status_code, 401)
