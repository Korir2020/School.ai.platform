from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

LOGIN, REFRESH = "/api/auth/login/", "/api/auth/refresh/"
CRED = {"username": "tom", "password": "pass-12345"}


@override_settings(REFRESH_IN_BODY=False)
class ProdCookieTests(APITestCase):
    def setUp(self):
        User.objects.create_user("tom", password="pass-12345")

    def test_login_body_has_no_refresh_but_cookie_does(self):
        r = self.client.post(LOGIN, CRED)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("refresh", r.json())
        self.assertIn("access", r.json())
        self.assertTrue(r.cookies["marian_rt"].value)

    def test_refresh_body_has_no_refresh_and_rotates_cookie(self):
        first = self.client.post(LOGIN, CRED).cookies["marian_rt"].value
        r = self.client.post(REFRESH, {}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("refresh", r.json())
        self.assertNotEqual(r.cookies["marian_rt"].value, first)
