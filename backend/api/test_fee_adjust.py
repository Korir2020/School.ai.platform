from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from api import test_fee_billing as tfb
from schools.models import AcademicYear, FeeAdjustment, StudentFee


class FeeAdjustTests(APITestCase):
    setUp = tfb.FeeBillingTests.setUp
    make = tfb.FeeBillingTests.make
    post = tfb.FeeBillingTests.post

    def bill(self, student, name="Tuition"):
        return StudentFee.objects.get(student=student, fee_structure__name=name)

    def adjust(self, bill, **data):
        return self.client.post(f"/api/fees/invoices/{bill.id}/adjust/", data, format="json")

    def test_set_amount_records_history(self):
        self.post()
        b = self.bill(self.day3)
        r = self.adjust(b, mode="set", value="18000", reason="Bursary discount")
        self.assertEqual(r.status_code, 200, r.data)
        b.refresh_from_db()
        self.assertEqual(b.amount_due, Decimal("18000"))
        self.assertTrue(b.manually_adjusted)
        self.assertEqual(FeeAdjustment.objects.filter(student_fee=b).count(), 1)
        self.assertEqual(r.data["history"][0]["reason"], "Bursary discount")
        r = self.client.get(f"/api/fees/invoices/{b.id}/adjust/")
        self.assertEqual(r.data["invoice"]["balance"], "18000.00")

    def test_adjust_after_payment_updates_status(self):
        self.post()
        b = self.bill(self.day3)
        b.amount_paid = Decimal("5000")
        b.status = "partial"
        b.save()
        r = self.adjust(b, mode="change", value="-15000", reason="Fee reduced")
        self.assertEqual(r.status_code, 200, r.data)
        b.refresh_from_db()
        self.assertEqual(b.amount_due, Decimal("5000"))
        self.assertEqual(b.status, "paid")
        r = self.adjust(b, mode="change", value="2000", reason="Trip added")
        b.refresh_from_db()
        self.assertEqual(b.amount_due, Decimal("7000"))
        self.assertEqual(b.status, "partial")

    def test_cannot_go_below_paid_and_reason_is_required(self):
        self.post()
        b = self.bill(self.day3)
        b.amount_paid = Decimal("5000")
        b.status = "partial"
        b.save()
        self.assertEqual(self.adjust(b, mode="set", value="4000", reason="Oops").status_code, 400)
        self.assertEqual(self.adjust(b, mode="set", value="9000", reason="").status_code, 400)
        self.assertEqual(self.adjust(b, mode="set", value="abc", reason="Bad").status_code, 400)
        b.refresh_from_db()
        self.assertEqual(b.amount_due, Decimal("20000"))

    def test_fee_edit_does_not_overwrite_adjusted_bill(self):
        fid = self.post().data["id"]
        b = self.bill(self.day3)
        self.adjust(b, mode="set", value="18000", reason="Bursary")
        r = self.client.patch(f"/api/fees/structures/{fid}/", {"amount": "25000"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        b.refresh_from_db()
        self.assertEqual(b.amount_due, Decimal("18000"))
        self.assertEqual(self.bill(self.boarder3).amount_due, Decimal("25000"))

    def test_other_school_bill_is_not_found(self):
        self.post()
        year = AcademicYear.objects.create(
            school=self.other, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.assertEqual(
            self.client.get("/api/fees/invoices/999999/adjust/").status_code, 404)
        self.assertEqual(year.school_id, self.other.id)

    def test_statement_works_for_unpaid_learner(self):
        self.post()
        r = self.client.get(f"/api/fees/students/{self.day3.id}/statement/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["totals"]["balance"], "20000.00")
        self.assertEqual(r.data["totals"]["paid"], "0.00")
        self.assertEqual(r.data["payments"], [])
        self.assertEqual(len(r.data["bills"]), 1)
        self.assertEqual(
            self.client.get(f"/api/fees/students/{self.outsider.id}/statement/").status_code, 404)

    def test_fee_lists_are_limited_to_the_bursars_school(self):
        other_year = AcademicYear.objects.create(
            school=self.other, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        years = {y["id"] for y in self.client.get("/api/fees/years/").data}
        self.assertIn(self.year.id, years)
        self.assertNotIn(other_year.id, years)
        ids = {s["id"] for s in self.client.get("/api/fees/students/").data}
        self.assertIn(self.day3.id, ids)
        self.assertNotIn(self.outsider.id, ids)
        self.assertEqual(self.client.get("/api/fees/terms/").status_code, 200)
