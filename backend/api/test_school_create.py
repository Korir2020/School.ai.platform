from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import MarkAuditLog, School, SchoolAdminProfile

URL = "/api/schools/"
BODY = {"name": "New School", "code": "NS1", "admin_username": "nsadmin",
        "admin_password": "Str0ng-pass-91", "admin_first_name": "Ann"}


class SchoolCreateTests(APITestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", password="pass12345")
        a = School.objects.create(name="A", code="A1")
        self.admin = User.objects.create_user("boss", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=a)

    def post(self, user, body=BODY):
        self.client.force_authenticate(user)
        return self.client.post(URL, body, format="json")

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.post(URL, BODY, format="json").status_code, 401)

    def test_school_admin_gets_403(self):
        self.assertEqual(self.post(self.admin).status_code, 403)
        self.assertFalse(School.objects.filter(code="NS1").exists())

    def test_superuser_creates_school_and_first_admin(self):
        self.assertEqual(self.post(self.root).status_code, 201)
        p = SchoolAdminProfile.objects.get(user__username="nsadmin")
        self.assertFalse(p.is_deputy)
        self.assertEqual(p.school.code, "NS1")
        self.assertTrue(MarkAuditLog.objects.filter(action="school_created").exists())

    def test_bad_input_rejected(self):
        self.client.force_authenticate(self.root)
        for bad in ({**BODY, "admin_password": "123"},
                    {**BODY, "admin_username": "boss"},
                    {**BODY, "name": ""}):
            self.assertEqual(self.client.post(URL, bad, format="json").status_code, 400)
        self.assertFalse(School.objects.filter(code="NS1").exists())

    def test_duplicate_code_rejected(self):
        self.assertEqual(self.post(self.root).status_code, 201)
        r = self.post(self.root, {**BODY, "admin_username": "other"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(username="other").exists())
