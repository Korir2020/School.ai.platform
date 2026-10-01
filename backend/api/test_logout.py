from django.contrib.auth.models import User
from rest_framework.test import APITestCase

LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/refresh/"
LOGOUT = "/api/auth/logout/"


class LogoutTests(APITestCase):
    def setUp(self):
        User.objects.create_user("tom", password="pass-12345")
        r = self.client.post(LOGIN, {"username": "tom", "password": "pass-12345"})
        self.refresh = r.json()["refresh"]

    def test_refresh_works_before_logout(self):
        r = self.client.post(REFRESH, {"refresh": self.refresh})
        self.assertEqual(r.status_code, 200)

    def test_logout_blacklists_refresh_token(self):
        r = self.client.post(LOGOUT, {"refresh": self.refresh})
        self.assertEqual(r.status_code, 205)
        r = self.client.post(REFRESH, {"refresh": self.refresh})
        self.assertEqual(r.status_code, 401)

    def test_logout_twice_is_rejected(self):
        self.client.post(LOGOUT, {"refresh": self.refresh})
        r = self.client.post(LOGOUT, {"refresh": self.refresh})
        self.assertEqual(r.status_code, 400)

    def test_missing_or_bad_token_is_400(self):
        self.assertEqual(self.client.post(LOGOUT, {}).status_code, 400)
        self.assertEqual(self.client.post(LOGOUT, {"refresh": "junk"}).status_code, 400)
