from decimal import Decimal

from rest_framework.test import APITestCase

from api import test_fee_billing as tfb
from api.fee_billing import bill_student
from schools.models import StudentFee


class AutoBillTests(APITestCase):
    setUp = tfb.FeeBillingTests.setUp
    make = tfb.FeeBillingTests.make
    post = tfb.FeeBillingTests.post
    URL = "/api/students/fee-category/"

    def activate(self):
        self.year.is_active = True
        self.year.save()

    def names(self, student):
        return sorted(f.fee_structure.name for f in StudentFee.objects.filter(student=student))

    def switch(self, student, category):
        return self.client.post(
            self.URL, {"students": [student.id], "category": category}, format="json")

    def test_late_learner_gets_missing_bills_once(self):
        self.activate()
        self.post()
        late = self.make("L1", "day", self.g3)
        self.assertEqual(bill_student(late), 1)
        self.assertEqual(bill_student(late), 0)
        self.assertEqual(self.names(late), ["Tuition"])

    def test_switch_swaps_unpaid_bills(self):
        self.activate()
        self.post(category="day")
        self.post(name="Boarding", category="boarder", amount="30000")
        self.assertEqual(self.names(self.day3), ["Tuition"])
        r = self.switch(self.day3, "boarder")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["students_changed"], 1)
        self.assertEqual(r.data["bills_removed"], 1)
        self.assertEqual(r.data["bills_created"], 1)
        self.assertEqual(self.names(self.day3), ["Boarding"])

    def test_paid_bill_is_kept_on_switch(self):
        self.activate()
        self.post(category="day")
        self.post(name="Boarding", category="boarder", amount="30000")
        fee = StudentFee.objects.get(student=self.day3, fee_structure__name="Tuition")
        fee.amount_paid = Decimal("1000")
        fee.status = "partial"
        fee.save()
        self.switch(self.day3, "boarder")
        self.assertEqual(self.names(self.day3), ["Boarding", "Tuition"])

    def test_other_school_and_bad_input(self):
        self.activate()
        r = self.switch(self.outsider, "boarder")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["students_changed"], 0)
        self.outsider.refresh_from_db()
        self.assertEqual(self.outsider.fee_category, "day")
        self.assertEqual(self.switch(self.day3, "weekly").status_code, 400)
        r = self.client.post(self.URL, {"students": [], "category": "day"}, format="json")
        self.assertEqual(r.status_code, 400)
