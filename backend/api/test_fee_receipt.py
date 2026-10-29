from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, FeePayment, FeeStructure, School, SchoolAdminProfile,
    StaffProfile, Student, StudentFee,
)


class FeeReceiptTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Fee School", code="FEE1")
        self.other = School.objects.create(name="Other", code="FEE2")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31))
        self.other_year = AcademicYear.objects.create(
            school=self.other, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31))
        self.student = Student.objects.create(
            school=self.school, first_name="A", last_name="Student", admission_number="A1")
        self.other_student = Student.objects.create(
            school=self.other, first_name="B", last_name="Student", admission_number="B1")
        self.admin = User.objects.create_user("feeadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.other_admin = User.objects.create_user("otheradmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=self.other)
        self.bursar = User.objects.create_user("bursar", password="pass12345")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.teacher = User.objects.create_user("feeteacher", password="pass12345")
        structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.year, name="Tuition",
            amount=Decimal("10000.00"), due_date=date(2026, 3, 31))
        self.invoice = StudentFee.objects.create(
            student=self.student, fee_structure=structure, amount_due=Decimal("10000.00"))
        other_structure = FeeStructure.objects.create(
            school=self.other, academic_year=self.other_year, name="Tuition",
            amount=Decimal("5000.00"), due_date=date(2026, 3, 31))
        self.other_invoice = StudentFee.objects.create(
            student=self.other_student, fee_structure=other_structure,
            amount_due=Decimal("5000.00"))

    def pay(self, invoice, amount, ref="", record=True):
        p = FeePayment.objects.create(
            student_fee=invoice, amount=Decimal(amount), method="cash",
            reference=ref, received_by=self.admin)
        if record:
            invoice.amount_paid += Decimal(amount)
            invoice.status = "paid" if invoice.amount_paid >= invoice.amount_due else "partial"
            invoice.save()
        return p

    def get(self, user, payment):
        self.client.force_authenticate(user=user)
        return self.client.get(f"/api/fees/payments/{payment.id}/receipt/")

    def test_status_at_payment_is_not_the_status_now(self):
        first = self.pay(self.invoice, "4000")
        second = self.pay(self.invoice, "6000")
        r1 = self.get(self.admin, first).json()
        r2 = self.get(self.admin, second).json()
        self.assertEqual(r1["fee"]["status"], "paid")
        self.assertEqual(r1["status_at_payment"], "partial")
        self.assertEqual(r2["status_at_payment"], "paid")

    def test_status_at_payment_hidden_when_balances_unverified(self):
        p = self.pay(self.invoice, "100", record=False)
        r = self.get(self.admin, p).json()
        self.assertFalse(r["balances_verified"])
        self.assertIsNone(r["status_at_payment"])

    def test_admin_and_bursar_read_own_receipt(self):
        p = self.pay(self.invoice, "4000.00", "MP1")
        for user in (self.admin, self.bursar):
            r = self.get(user, p)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data["receipt_number"], f"RCPT-FEE1-{p.id:06d}")
            self.assertEqual(r.data["school"]["name"], "Fee School")
            self.assertEqual(r.data["school"]["currency"], "KES")
            self.assertEqual(r.data["student"]["admission_number"], "A1")
            self.assertEqual(r.data["payment"]["reference"], "MP1")
            self.assertTrue(r.data["balances_verified"])
            self.assertEqual(Decimal(r.data["previous_balance"]), Decimal("10000.00"))
            self.assertEqual(Decimal(r.data["balance_after"]), Decimal("6000.00"))

    def test_second_payment_balances(self):
        self.pay(self.invoice, "4000.00", "A")
        p2 = self.pay(self.invoice, "1000.00", "B")
        r = self.get(self.admin, p2)
        self.assertEqual(Decimal(r.data["previous_balance"]), Decimal("6000.00"))
        self.assertEqual(Decimal(r.data["balance_after"]), Decimal("5000.00"))

    def test_currency_comes_from_school(self):
        self.school.currency = "UGX"
        self.school.save()
        p = self.pay(self.invoice, "100.00")
        self.assertEqual(self.get(self.admin, p).data["school"]["currency"], "UGX")

    def test_teacher_forbidden(self):
        p = self.pay(self.invoice, "100.00")
        self.assertEqual(self.get(self.teacher, p).status_code, 403)

    def test_anonymous_blocked(self):
        p = self.pay(self.invoice, "100.00")
        self.client.force_authenticate(user=None)
        r = self.client.get(f"/api/fees/payments/{p.id}/receipt/")
        self.assertIn(r.status_code, (401, 403))

    def test_cross_school_returns_404(self):
        p = self.pay(self.other_invoice, "100.00")
        r = self.get(self.admin, p)
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("Other", str(r.data))
        self.assertEqual(self.get(self.other_admin, p).status_code, 200)

    def test_missing_payment_404(self):
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.get("/api/fees/payments/999999/receipt/").status_code, 404)

    def test_get_changes_nothing(self):
        p = self.pay(self.invoice, "4000.00")
        before = (FeePayment.objects.count(), self.invoice.amount_paid, self.invoice.status)
        for _ in range(3):
            self.get(self.admin, p)
        self.invoice.refresh_from_db()
        after = (FeePayment.objects.count(), self.invoice.amount_paid, self.invoice.status)
        self.assertEqual(before, after)

    def test_post_not_allowed(self):
        p = self.pay(self.invoice, "100.00")
        self.client.force_authenticate(user=self.admin)
        r = self.client.post(f"/api/fees/payments/{p.id}/receipt/", {})
        self.assertEqual(r.status_code, 405)

    def test_waived_fee_has_no_balances(self):
        p = self.pay(self.invoice, "4000.00")
        self.invoice.status = "waived"
        self.invoice.save()
        r = self.get(self.admin, p)
        self.assertFalse(r.data["balances_verified"])
        self.assertIsNone(r.data["previous_balance"])
        self.assertIsNone(r.data["balance_after"])
        self.assertEqual(r.data["fee"]["status"], "waived")

    def test_unreconciled_payments_have_no_balances(self):
        p = self.pay(self.invoice, "4000.00", record=False)
        r = self.get(self.admin, p)
        self.assertFalse(r.data["balances_verified"])
        self.assertIsNone(r.data["balance_after"])
