from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, FeeStructure, School, SchoolAdminProfile, StaffProfile,
    Student, StudentFee,
)


class FeeApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Fee School", code="FEE1")
        self.other = School.objects.create(name="Other", code="FEE2")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.student = Student.objects.create(
            school=self.school, first_name="A", last_name="Student", admission_number="A1"
        )
        self.other_student = Student.objects.create(
            school=self.other, first_name="B", last_name="Student", admission_number="B1"
        )
        self.admin = User.objects.create_user("feeadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.bursar = User.objects.create_user("bursar", password="pass12345")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.teacher = User.objects.create_user("feeteacher", password="pass12345")
        structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.year, name="Tuition",
            amount=Decimal("10000.00"), due_date=date(2026, 3, 31),
        )
        self.invoice = StudentFee.objects.create(
            student=self.student, fee_structure=structure, amount_due=Decimal("10000.00")
        )

    def test_admin_can_read_summary_and_bursar_can_read_invoices(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/fees/summary/").status_code, 200)
        self.client.force_authenticate(self.bursar)
        result = self.client.get("/api/fees/invoices/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()[0]["balance"], "10000.00")

    def test_bursar_payment_updates_balance(self):
        self.client.force_authenticate(self.bursar)
        result = self.client.post("/api/fees/payments/", {
            "student_fee": self.invoice.id, "amount": "2500", "method": "mpesa",
            "reference": "ABC123",
        }, format="json")
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()["status"], "partial")
        self.assertEqual(result.json()["balance"], "7500.00")

    def test_payment_response_includes_payment_id(self):
        self.client.force_authenticate(self.bursar)
        first = self._pay()
        self.assertEqual(first.status_code, 201)
        second = self._pay()
        self.assertEqual(second.status_code, 201)
        first_id = first.json()["payment_id"]
        second_id = second.json()["payment_id"]
        self.assertIsInstance(first_id, int)
        self.assertNotEqual(first_id, second_id)

    def test_teacher_and_anonymous_are_blocked(self):
        self.assertEqual(self.client.get("/api/fees/summary/").status_code, 401)
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get("/api/fees/summary/").status_code, 403)

    def test_payment_cannot_exceed_balance(self):
        self.client.force_authenticate(self.admin)
        result = self.client.post("/api/fees/payments/", {
            "student_fee": self.invoice.id, "amount": "10001", "method": "cash",
        }, format="json")
        self.assertEqual(result.status_code, 400)

    def test_history_and_report_are_school_scoped(self):
        self.client.force_authenticate(self.bursar)
        self.assertEqual(self.client.get("/api/fees/payment-history/").status_code, 200)
        report = self.client.get("/api/fees/report/")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()[0]["balance"], "10000.00")

    def test_bursar_can_waive(self):
        self.client.force_authenticate(self.bursar)
        result = self.client.post(
            f"/api/fees/invoices/{self.invoice.id}/waive/",
            {"reason": "Bursary"}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "waived")

    def test_admin_can_waive(self):
        self.client.force_authenticate(self.admin)
        result = self.client.post(
            f"/api/fees/invoices/{self.invoice.id}/waive/",
            {"reason": "Bursary"}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "waived")


    def _pay(self, **extra):
        body = {"student_fee": self.invoice.id, "amount": "100", "method": "cash"}
        body.update(extra)
        return self.client.post("/api/fees/payments/", body, format="json")

    def test_bad_amounts_are_rejected_without_leaking_errors(self):
        self.client.force_authenticate(self.admin)
        for bad in ["abc", "", "NaN", "Infinity", "-5", "0", "10.005", None]:
            result = self._pay(amount=bad)
            self.assertEqual(result.status_code, 400, bad)
            self.assertNotIn("InvalidOperation", str(result.json()))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("0.00"))

    def test_unknown_or_malformed_invoice_is_404(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self._pay(student_fee=999999).status_code, 404)
        self.assertEqual(self._pay(student_fee="x").status_code, 404)

    def test_duplicate_reference_is_rejected_once_recorded(self):
        self.client.force_authenticate(self.bursar)
        self.assertEqual(self._pay(method="mpesa", reference="QWE123").status_code, 201)
        self.assertEqual(self._pay(method="mpesa", reference="qwe123").status_code, 409)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("100.00"))
        self.assertEqual(self.invoice.payments.count(), 1)

    def test_blank_references_are_allowed_repeatedly(self):
        self.client.force_authenticate(self.bursar)
        self.assertEqual(self._pay().status_code, 201)
        self.assertEqual(self._pay().status_code, 201)

    def test_negative_amounts_are_rejected(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/fees/structures/", {
            "academic_year": self.year.id, "name": "Bad", "amount": "-5"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/fees/invoices/", {
            "student": self.student.id, "fee_structure": self.invoice.fee_structure_id,
            "amount_due": "-1"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_waived_invoice_is_not_counted_as_owed(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(
            f"/api/fees/invoices/{self.invoice.id}/waive/", {}, format="json").status_code, 200)
        data = self.client.get("/api/fees/summary/").json()
        self.assertEqual(data["balance"], "0.00")
        self.assertEqual(data["overdue"], 0)
