from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APITestCase

from api import test_fee_billing as tfb
from api.fee_billing import carry_forward
from schools.models import AcademicYear, FeeStructure, StudentFee, Term


class ArrearsTests(APITestCase):
    setUp = tfb.FeeBillingTests.setUp
    make = tfb.FeeBillingTests.make
    post = tfb.FeeBillingTests.post

    def term(self, name, start, end):
        today = date.today()
        return Term.objects.create(
            academic_year=self.year, name=name,
            start_date=today + timedelta(days=start),
            end_date=today + timedelta(days=end))

    def fee(self, student, name):
        return StudentFee.objects.get(student=student, fee_structure__name=name)

    def test_unpaid_balance_moves_to_next_term_once(self):
        t1 = self.term("Term 1", -200, -100)
        t2 = self.term("Term 2", -90, 30)
        self.post(term=t1.id)
        paid = self.fee(self.day3, "Tuition")
        paid.amount_paid = Decimal("5000")
        paid.status = "partial"
        paid.save()
        r = self.post(name="Lunch", term=t2.id, amount="3000")
        self.assertEqual(r.status_code, 201, r.data)
        lunch = self.fee(self.day3, "Lunch")
        self.assertEqual(lunch.amount_due, Decimal("18000"))
        self.assertEqual(lunch.balance_brought_forward, Decimal("15000"))
        old = self.fee(self.day3, "Tuition")
        self.assertEqual(old.amount_due, Decimal("5000"))
        self.assertEqual(old.carried_out, Decimal("15000"))
        self.assertEqual(old.status, "paid")
        self.assertEqual(self.fee(self.boarder3, "Lunch").amount_due, Decimal("23000"))
        self.assertEqual(carry_forward(self.day3, t2), 0)
        lunch.refresh_from_db()
        self.assertEqual(lunch.amount_due, Decimal("18000"))

    def test_term_that_has_not_ended_is_not_carried(self):
        a = self.term("Term A", -10, 20)
        b = self.term("Term B", 30, 90)
        self.post(term=a.id)
        self.post(name="Lunch", term=b.id, amount="3000")
        lunch = self.fee(self.day3, "Lunch")
        self.assertEqual(lunch.amount_due, Decimal("3000"))
        self.assertEqual(lunch.balance_brought_forward, Decimal("0"))
        r = self.client.post("/api/fees/carry-forward/", {"term": b.id}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_endpoint_carries_when_run_later(self):
        t1 = self.term("Term 1", -200, -100)
        t2 = self.term("Term 2", -90, 30)
        self.post(term=t1.id)
        fs = FeeStructure.objects.create(
            school=self.school, academic_year=self.year, name="Lunch",
            amount=Decimal("3000"), term=t2)
        StudentFee.objects.create(
            student=self.day3, fee_structure=fs, amount_due=Decimal("3000"))
        r = self.client.post("/api/fees/carry-forward/", {"term": t2.id}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["students_carried"], 1)
        self.assertEqual(self.fee(self.day3, "Lunch").amount_due, Decimal("23000"))

    def test_other_school_term_is_not_found(self):
        year = AcademicYear.objects.create(
            school=self.other, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        t = Term.objects.create(
            academic_year=year, name="T",
            start_date=date(2026, 1, 1), end_date=date(2026, 4, 1))
        r = self.client.post("/api/fees/carry-forward/", {"term": t.id}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_editing_amount_keeps_arrears(self):
        t1 = self.term("Term 1", -200, -100)
        t2 = self.term("Term 2", -90, 30)
        self.post(term=t1.id)
        self.post(name="Lunch", term=t2.id, amount="3000")
        lid = FeeStructure.objects.get(name="Lunch").id
        r = self.client.patch(f"/api/fees/structures/{lid}/", {"amount": "4000"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.fee(self.day3, "Lunch").amount_due, Decimal("24000"))
