from rest_framework.test import APITestCase

from api import test_fee_billing as tfb
from schools.models import Student, StudentFee


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
        r = self.client.post("/api/enrollments/", {
            "student": late.id, "academic_year": self.year.id,
            "class_level": self.g3.id, "is_active": True}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(StudentFee.objects.filter(student=late).count(), 1)
