from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from api import test_fee_billing as tfb
from schools.models import SchoolAdminProfile, Student, StudentFee


class EnrollBillingTests(APITestCase):
    setUp = tfb.FeeBillingTests.setUp
    make = tfb.FeeBillingTests.make
    post = tfb.FeeBillingTests.post

    def test_enrolling_a_new_learner_bills_them(self):
        self.year.is_active = True
        self.year.save()
        self.post(category="day")
        late = Student.objects.create(
            school=self.school, first_name="Late", last_name="Joiner",
            admission_number="LATE1", fee_category="day")
        self.assertEqual(StudentFee.objects.filter(student=late).count(), 0)
        admin = User.objects.create_user("billadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=admin, school=self.school)
        self.client.force_authenticate(admin)
        r = self.client.post("/api/enrollments/", {
            "student": late.id, "academic_year": self.year.id,
            "class_level": self.g3.id, "is_active": True}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(StudentFee.objects.filter(student=late).count(), 1)
