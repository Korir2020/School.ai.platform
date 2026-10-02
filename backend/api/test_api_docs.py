from django.contrib.auth.models import User
from rest_framework.test import APITestCase

SCHEMA = "/api/schema/"
DOCS = "/api/docs/"


class ApiDocsTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("boss", password="pass-12345")
        self.plain = User.objects.create_user("tom", password="pass-12345")

    def test_anonymous_is_blocked(self):
        for url in (SCHEMA, DOCS):
            self.assertIn(self.client.get(url).status_code, (401, 403))

    def test_non_admin_is_blocked(self):
        self.client.force_authenticate(self.plain)
        for url in (SCHEMA, DOCS):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_gets_200(self):
        self.client.force_authenticate(self.admin)
        for url in (SCHEMA, DOCS):
            self.assertEqual(self.client.get(url).status_code, 200)
