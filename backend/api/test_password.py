from django.contrib.auth.models import User
from rest_framework.test import APITestCase

LOGIN = "/api/auth/login/"
URL = "/api/auth/change-password/"


class ChangePasswordTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("tom", password="old-pass-12345")
        r = self.client.post(LOGIN, {"username": "tom", "password": "old-pass-12345"})
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + r.json()["access"])

    def test_requires_login(self):
        self.client.credentials()
        r = self.client.post(URL, {"old_password": "x", "new_password": "y"})
        self.assertEqual(r.status_code, 401)

    def test_wrong_old_password(self):
        r = self.client.post(URL, {"old_password": "nope", "new_password": "Brand-new-7391"})
        self.assertEqual(r.status_code, 400)

    def test_weak_new_password_rejected(self):
        r = self.client.post(URL, {"old_password": "old-pass-12345", "new_password": "12345678"})
        self.assertEqual(r.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-pass-12345"))

    def test_same_password_rejected(self):
        r = self.client.post(URL, {"old_password": "old-pass-12345", "new_password": "old-pass-12345"})
        self.assertEqual(r.status_code, 400)

    def test_change_works_and_new_login_succeeds(self):
        r = self.client.post(URL, {"old_password": "old-pass-12345", "new_password": "Brand-new-7391"})
        self.assertEqual(r.status_code, 200)
        self.client.credentials()
        self.assertEqual(self.client.post(LOGIN, {"username": "tom", "password": "old-pass-12345"}).status_code, 401)
        self.assertEqual(self.client.post(LOGIN, {"username": "tom", "password": "Brand-new-7391"}).status_code, 200)
