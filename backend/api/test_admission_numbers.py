from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import School, SchoolAdminProfile, Student

BODY = {"first_name": "New", "last_name": "Kid", "admission_number": "001"}


class AdmissionNumberTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.admin_a = User.objects.create_user("admin_a", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_a, school=self.a)
        self.admin_b = User.objects.create_user("admin_b", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_b, school=self.b)

    def test_same_number_allowed_in_different_schools(self):
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.post("/api/students/", BODY, format="json").status_code, 201)
        self.client.force_authenticate(self.admin_b)
        self.assertEqual(self.client.post("/api/students/", BODY, format="json").status_code, 201)
        self.assertEqual(Student.objects.filter(admission_number="001").count(), 2)

    def test_duplicate_in_same_school_rejected(self):
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.post("/api/students/", BODY, format="json").status_code, 201)
        self.assertEqual(self.client.post("/api/students/", BODY, format="json").status_code, 400)
