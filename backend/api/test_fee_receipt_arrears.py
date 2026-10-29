from decimal import Decimal

from api.test_fee_receipt import FeeReceiptTests as Base
from rest_framework.test import APITestCase
from schools.models import FeePayment


class ReceiptArrearsTests(APITestCase):
    setUp = Base.setUp

    def test_receipt_shows_category_and_balance_brought_forward(self):
        fee = self.invoice
        fee.balance_brought_forward = Decimal("2000")
        fee.amount_due = Decimal("12000")
        fee.amount_paid = Decimal("1000")
        fee.status = "partial"
        fee.save()
        p = FeePayment.objects.create(
            student_fee=fee, amount=Decimal("1000"), method="cash",
            received_by=self.admin)
        self.client.force_authenticate(self.admin)
        r = self.client.get(f"/api/fees/payments/{p.id}/receipt/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(str(r.data["fee"]["balance_brought_forward"])), Decimal("2000"))
        self.assertEqual(r.data["fee"]["category"], "day")
        self.assertEqual(Decimal(str(r.data["fee"]["amount_due"])), Decimal("12000"))
