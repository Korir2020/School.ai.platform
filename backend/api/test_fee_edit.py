from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from api import test_fee_billing as tfb
from schools.models import AcademicYear, FeeStructure, StudentFee


class FeeEditTests(APITestCase):
    setUp = tfb.FeeBillingTests.setUp
    make = tfb.FeeBillingTests.make
    post = tfb.FeeBillingTests.post

    def url(self, pk):
        return f"/api/fees/structures/{pk}/"

    def test_edit_amount_updates_unpaid_fees(self):
        fid = self.post().data["id"]
        r = self.client.patch(self.url(fid), {"amount": "25000"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["students_updated"], 3)
        self.assertEqual(r.data["students_billed"], 0)
        for s in (self.day3, self.boarder3, self.day8):
            fee = StudentFee.objects.get(student=s, fee_structure_id=fid)
            self.assertEqual(fee.amount_due, Decimal("25000"))

    def test_widening_grades_bills_only_new_learners(self):
        fid = self.post(category="day", from_grade=1, to_grade=5).data["id"]
        self.assertEqual(StudentFee.objects.filter(fee_structure_id=fid).count(), 1)
        r = self.client.patch(self.url(fid), {"to_grade": 9}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["students_billed"], 1)
        self.assertEqual(StudentFee.objects.filter(fee_structure_id=fid).count(), 2)

    def test_paid_fee_keeps_its_amount(self):
        fid = self.post().data["id"]
        paid = StudentFee.objects.get(student=self.day3, fee_structure_id=fid)
        paid.amount_paid = Decimal("5000")
        paid.save()
        r = self.client.patch(self.url(fid), {"amount": "25000"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["students_updated"], 2)
        paid.refresh_from_db()
        self.assertEqual(paid.amount_due, Decimal("20000"))

    def test_bad_grade_range_is_rejected(self):
        fid = self.post().data["id"]
        r = self.client.patch(self.url(fid), {"from_grade": 9, "to_grade": 2}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_other_school_fee_is_not_found(self):
        year = AcademicYear.objects.create(
            school=self.other, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        x = FeeStructure.objects.create(
            school=self.other, academic_year=year, name="Tuition", amount=Decimal("100"))
        r = self.client.patch(self.url(x.id), {"amount": "5"}, format="json")
        self.assertEqual(r.status_code, 404)
