from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from api.receipt_verify import make_token
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, FeePayment, FeeStructure, GuardianProfile, School,
    SchoolAdminProfile, StaffProfile, Student, StudentFee, StudentGuardian,
    TeacherProfile, Term,
)


class CoreFeePrivacyTests(APITestCase):
    denied_detail = "You do not have permission to access fee information."

    def setUp(self):
        self.school = School.objects.create(name="Core Fee School", code="CORE1")
        self.other_school = School.objects.create(name="Other Fee School", code="CORE2")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31), is_active=True,
        )
        self.old_year = AcademicYear.objects.create(
            school=self.school, name="2025", start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31), is_active=False,
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 30),
        )
        self.old_term = Term.objects.create(
            academic_year=self.old_year, name="Term 3", start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 31),
        )
        self.future_year = AcademicYear.objects.create(
            school=self.school, name="2027", start_date=date(2027, 1, 1),
            end_date=date(2027, 12, 31), is_active=True,
        )
        curriculum = Curriculum.objects.create(name="Core curriculum", code="CORE-CBC")
        self.level_one = ClassLevel.objects.create(
            curriculum=curriculum, name="Grade 1", level_number=1,
        )
        self.level_two = ClassLevel.objects.create(
            curriculum=curriculum, name="Grade 2", level_number=2,
        )
        self.student = Student.objects.create(
            school=self.school, first_name="Amina", last_name="Learner",
            admission_number="CORE-A1", fee_category="day",
        )
        self.other_student = Student.objects.create(
            school=self.other_school, first_name="Other", last_name="Learner",
            admission_number="CORE-B1",
        )
        self.structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.year, term=self.term,
            name="Tuition", amount=Decimal("100.00"),
        )
        self.future_structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.future_year,
            name="Future tuition", amount=Decimal("200.00"),
        )
        self.invoice = StudentFee.objects.create(
            student=self.student, fee_structure=self.structure,
            amount_due=Decimal("100.00"),
        )
        other_year = AcademicYear.objects.create(
            school=self.other_school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        other_structure = FeeStructure.objects.create(
            school=self.other_school, academic_year=other_year,
            name="Other tuition", amount=Decimal("900.00"),
        )
        self.other_invoice = StudentFee.objects.create(
            student=self.other_student, fee_structure=other_structure,
            amount_due=Decimal("900.00"),
        )
        self.admin = self.make_user("core_admin")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.bursar = self.make_user("core_bursar")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.deputy = self.make_user("core_deputy")
        SchoolAdminProfile.objects.create(
            user=self.deputy, school=self.school, is_deputy=True,
        )
        self.teacher = self.make_user("core_teacher")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.secretary = self.make_user("core_secretary")
        StaffProfile.objects.create(
            user=self.secretary, school=self.school, role="secretary",
        )
        self.parent = self.make_user("core_parent")
        self.parent_guardian = GuardianProfile.objects.create(
            user=self.parent, school=self.school,
        )
        self.other_admin = self.make_user("core_other_admin")
        SchoolAdminProfile.objects.create(
            user=self.other_admin, school=self.other_school,
        )
        self.superuser = User.objects.create_superuser(
            "core_root", "root@example.test", "pass12345",
        )
        self.payment = FeePayment.objects.create(
            student_fee=self.invoice, amount=Decimal("10.00"), method="mpesa",
            reference="CORE-PAY-1", received_by=self.bursar,
        )
        self.invoice.amount_paid = Decimal("10.00")
        self.invoice.status = "partial"
        self.invoice.save()

    @staticmethod
    def make_user(username):
        return User.objects.create_user(username, password="pass12345")

    def get(self, user, path):
        self.client.force_authenticate(user=user)
        return self.client.get(path)

    def post(self, user, path, data):
        self.client.force_authenticate(user=user)
        return self.client.post(path, data, format="json")

    def patch(self, user, path, data):
        self.client.force_authenticate(user=user)
        return self.client.patch(path, data, format="json")

    def fee_surface_calls(self):
        """Return calls exercising every owned fee handler with valid payloads."""
        return [
            ("summary", lambda u: self.get(u, "/api/fees/summary/")),
            ("structures list", lambda u: self.get(u, "/api/fees/structures/")),
            ("structure create", lambda u: self.post(u, "/api/fees/structures/", {
                "academic_year": self.year.id, "name": f"Role check structure {u.id}",
                "amount": "25.00", "term": self.term.id,
            })),
            ("structure detail", lambda u: self.patch(
                u, f"/api/fees/structures/{self.structure.id}/", {"description": "Updated"},
            )),
            ("invoice list", lambda u: self.get(u, "/api/fees/invoices/")),
            ("invoice create", lambda u: self.create_invoice_for(u)),
            ("payment recording", lambda u: self.post(u, "/api/fees/payments/", {
                "student_fee": self.invoice.id, "amount": "1.00", "method": "cash",
            })),
            ("payment history", lambda u: self.get(u, "/api/fees/payment-history/")),
            ("waive", lambda u: self.post(
                u, f"/api/fees/invoices/{self.invoice.id}/waive/", {"reason": "Aid"},
            )),
            ("report", lambda u: self.get(u, "/api/fees/report/")),
            ("receipt", lambda u: self.get(
                u, f"/api/fees/payments/{self.payment.id}/receipt/",
            )),
            ("category collection", lambda u: self.post(
                u, "/api/students/fee-category/",
                {"students": [self.student.id], "category": "boarder"},
            )),
            ("carry forward", lambda u: self.post(
                u, "/api/fees/carry-forward/", {"term": self.term.id},
            )),
            ("adjust read", lambda u: self.get(
                u, f"/api/fees/invoices/{self.invoice.id}/adjust/",
            )),
            ("adjust write", lambda u: self.post(
                u, f"/api/fees/invoices/{self.invoice.id}/adjust/",
                {"mode": "change", "value": "1.00", "reason": "Test change"},
            )),
            ("statement", lambda u: self.get(
                u, f"/api/fees/students/{self.student.id}/statement/",
            )),
            ("years", lambda u: self.get(u, "/api/fees/years/")),
            ("terms", lambda u: self.get(u, "/api/fees/terms/")),
            ("students", lambda u: self.get(u, "/api/fees/students/")),
            ("student fee-category PATCH", lambda u: self.patch(
                u, f"/api/students/{self.student.id}/", {"fee_category": "boarder"},
            )),
        ]

    def create_invoice_for(self, user):
        structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.year,
            name=f"Invoice creation {user.id}", amount=Decimal("120.00"),
        )
        return self.post(user, "/api/fees/invoices/", {
            "student": self.student.id, "fee_structure": structure.id,
            "amount_due": "120.00",
        })

    def test_non_fee_roles_get_generic_403_for_every_fee_handler(self):
        denied_users = (
            self.deputy, self.teacher, self.secretary, self.parent, self.superuser,
        )
        for user in denied_users:
            for surface, call in self.fee_surface_calls():
                with self.subTest(user=user.username, surface=surface):
                    response = call(user)
                    self.assertEqual(response.status_code, 403, response.data)
                    self.assertEqual(response.data.get("detail"), self.denied_detail)

    def test_school_admin_and_bursar_can_reach_every_fee_handler(self):
        for user in (self.admin, self.bursar):
            for surface, call in self.fee_surface_calls():
                with self.subTest(user=user.username, surface=surface):
                    response = call(user)
                    self.assertNotIn(response.status_code, (401, 403), response.data)

    def test_other_school_admin_gets_generic_403_for_foreign_fee_targets(self):
        calls = [
            lambda: self.post(self.other_admin, "/api/fees/structures/", {
                "academic_year": self.year.id, "name": "Foreign structure",
                "amount": "1.00",
            }),
            lambda: self.patch(self.other_admin, f"/api/fees/structures/{self.structure.id}/", {"name": "X"}),
            lambda: self.get(self.other_admin, f"/api/fees/invoices/?student={self.student.id}"),
            lambda: self.post(self.other_admin, "/api/fees/invoices/", {
                "student": self.student.id, "fee_structure": self.structure.id,
                "amount_due": "1.00",
            }),
            lambda: self.post(self.other_admin, "/api/fees/payments/", {
                "student_fee": self.invoice.id, "amount": "1.00",
            }),
            lambda: self.get(self.other_admin, f"/api/fees/payment-history/?student_fee={self.invoice.id}"),
            lambda: self.post(self.other_admin, f"/api/fees/invoices/{self.invoice.id}/waive/", {}),
            lambda: self.get(self.other_admin, f"/api/fees/payments/{self.payment.id}/receipt/"),
            lambda: self.post(self.other_admin, "/api/students/fee-category/", {
                "students": [self.student.id], "category": "boarder",
            }),
            lambda: self.post(self.other_admin, "/api/fees/carry-forward/", {"term": self.term.id}),
            lambda: self.get(self.other_admin, f"/api/fees/invoices/{self.invoice.id}/adjust/"),
            lambda: self.post(self.other_admin, f"/api/fees/invoices/{self.invoice.id}/adjust/", {
                "mode": "change", "value": "1.00", "reason": "Not allowed",
            }),
            lambda: self.get(self.other_admin, f"/api/fees/students/{self.student.id}/statement/"),
            lambda: self.patch(self.other_admin, f"/api/students/{self.student.id}/", {"fee_category": "boarder"}),
        ]
        for index, call in enumerate(calls):
            with self.subTest(target=index):
                response = call()
                self.assertEqual(response.status_code, 403, response.data)
                self.assertEqual(response.data.get("detail"), self.denied_detail)

    def test_other_school_admin_collection_views_are_scoped_to_own_school(self):
        paths = (
            "/api/fees/summary/", "/api/fees/structures/", "/api/fees/invoices/",
            "/api/fees/payment-history/", "/api/fees/report/", "/api/fees/years/",
            "/api/fees/terms/", "/api/fees/students/",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.get(self.other_admin, path)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertNotIn("CORE-A1", str(response.data))
                self.assertNotIn("Core Fee School", str(response.data))

    def test_fee_lists_and_reports_are_strictly_school_scoped(self):
        self.client.force_authenticate(user=self.admin)
        for path in (
            "/api/fees/invoices/", "/api/fees/students/", "/api/fees/report/",
            "/api/fees/structures/", "/api/fees/payment-history/",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertNotIn("Other Fee School", str(response.data), path)
            self.assertNotIn("CORE-B1", str(response.data), path)
        cross_school_receipt = self.client.get(
            f"/api/fees/payments/{self.payment.id + 9000}/receipt/",
        )
        self.assertEqual(cross_school_receipt.status_code, 404)

    def test_parent_fee_screen_remains_own_child_only(self):
        parent = self.parent
        StudentGuardian.objects.create(
            student=self.student, guardian=self.parent_guardian,
        )
        self.client.force_authenticate(user=parent)
        own = self.client.get(f"/api/parent/children/{self.student.id}/fees/")
        other = self.client.get(f"/api/parent/children/{self.other_student.id}/fees/")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(len(own.data), 1)
        self.assertEqual(other.status_code, 404)

    def test_public_qr_verification_exposes_validity_only(self):
        path = f"/api/fees/receipt-verify/{make_token(self.payment.id)}/"
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn("Valid receipt", text)
        for private_value in (
            "Core Fee School", "CORE1", "Amina Learner", "CORE-A1", "10.00",
            "2026", "CORE-PAY-1",
        ):
            self.assertNotIn(private_value, text)
        self.assertEqual(response["Cache-Control"], "no-store")
        invalid = self.client.get("/api/fees/receipt-verify/not-a-signed-token/")
        self.assertEqual(invalid.status_code, 404)
        self.assertIn("Not valid", invalid.content.decode())

    def test_authorized_payment_and_receipt_creation_are_preserved(self):
        response = self.post(self.bursar, "/api/fees/payments/", {
            "student_fee": self.invoice.id, "amount": "5.00", "method": "mpesa",
            "reference": "CORE-PAY-2",
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["balance"], "85.00")
        receipt = self.get(
            self.admin, f"/api/fees/payments/{response.data['payment_id']}/receipt/",
        )
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.data["payment"]["reference"], "CORE-PAY-2")

    def test_enrollment_promotion_and_readmission_billing_respect_fee_access(self):
        for user, prefix, expect_bills in (
            (self.admin, "authorized", True),
            (self.deputy, "deputy", False),
        ):
            enrolled = Student.objects.create(
                school=self.school, first_name=prefix, last_name="Enroll",
                admission_number=f"{prefix.upper()}-ENR",
            )
            self.client.force_authenticate(user=user)
            enrollment_response = self.client.post("/api/enrollments/", {
                "student": enrolled.id, "academic_year": self.year.id,
                "class_level": self.level_one.id, "is_active": True,
            }, format="json")
            self.assertEqual(enrollment_response.status_code, 201, enrollment_response.data)
            self.assertEqual(StudentFee.objects.filter(student=enrolled).exists(), expect_bills)

            promoted = Student.objects.create(
                school=self.school, first_name=prefix, last_name="Promote",
                admission_number=f"{prefix.upper()}-PRO",
            )
            Enrollment.objects.create(
                student=promoted, academic_year=self.year,
                class_level=self.level_one, is_active=True,
            )
            self.client.force_authenticate(user=user)
            promotion_response = self.client.post("/api/promotions/run/", {
                "from_year": self.year.id, "to_year": self.future_year.id,
            }, format="json")
            self.assertEqual(promotion_response.status_code, 200, promotion_response.data)
            self.assertEqual(StudentFee.objects.filter(student=promoted).exists(), expect_bills)

            readmitted = Student.objects.create(
                school=self.school, first_name=prefix, last_name="Readmit",
                admission_number=f"{prefix.upper()}-READ", status="left",
            )
            readmit_response = self.client.post(
                f"/api/students/{readmitted.id}/readmit/",
                {"class_level": self.level_one.id}, format="json",
            )
            self.assertEqual(readmit_response.status_code, 200, readmit_response.data)
            self.assertEqual(StudentFee.objects.filter(student=readmitted).exists(), expect_bills)
