from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, FeePayment, FeeStructure,
    GuardianProfile, MarkAuditLog, School, SchoolAdminProfile, StaffProfile,
    Student, StudentFee, Stream, StudentGuardian, Subject, TeacherAssignment,
    TeacherProfile, Term,
)


class EmbeddedFeePrivacyTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Fee School", code="FEE1")
        self.other_school = School.objects.create(name="Other Fee School", code="FEE2")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.other_year = AcademicYear.objects.create(
            school=self.other_school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 1),
        )
        self.other_term = Term.objects.create(
            academic_year=self.other_year, name="Term 1", start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 1),
        )
        curriculum = Curriculum.objects.create(name="Curriculum", code="FC")
        level = ClassLevel.objects.create(
            curriculum=curriculum, name="Grade 1", level_number=1,
        )
        self.stream = Stream.objects.create(
            school=self.school, class_level=level, name="Blue",
        )
        self.student = Student.objects.create(
            school=self.school, first_name="Amina", last_name="Learner",
            admission_number="F-1",
        )
        self.other_student = Student.objects.create(
            school=self.other_school, first_name="Other", last_name="Learner",
            admission_number="O-1",
        )
        Enrollment.objects.create(
            student=self.student, academic_year=self.year, class_level=level,
            stream=self.stream,
        )
        self.subject = Subject.objects.create(school=self.school, name="Math")

        self.admin = self._user("admin")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.other_admin = self._user("other_admin")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=self.other_school)
        self.deputy = self._user("deputy")
        SchoolAdminProfile.objects.create(
            user=self.deputy, school=self.school, is_deputy=True,
        )
        self.teacher = self._user("teacher")
        teacher_profile = TeacherProfile.objects.create(
            user=self.teacher, school=self.school,
        )
        TeacherAssignment.objects.create(
            teacher=teacher_profile, school=self.school, subject=self.subject,
            stream=self.stream,
        )
        self.bursar = self._user("bursar")
        StaffProfile.objects.create(
            user=self.bursar, school=self.school, role="bursar",
        )
        self.secretary = self._user("secretary")
        StaffProfile.objects.create(
            user=self.secretary, school=self.school, role="secretary",
        )
        self.parent = self._user("parent")
        guardian = GuardianProfile.objects.create(user=self.parent, school=self.school)
        StudentGuardian.objects.create(
            student=self.student, guardian=guardian, relationship="parent",
        )
        self.superuser = User.objects.create_superuser(
            "platform_root", "root@example.test", "pass12345",
        )

        self.structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.year, name="Tuition",
            amount=Decimal("500.00"),
        )
        self.invoice = StudentFee.objects.create(
            student=self.student, fee_structure=self.structure,
            amount_due=Decimal("500.00"), amount_paid=Decimal("125.00"),
            status="partial",
        )
        self.payment = FeePayment.objects.create(
            student_fee=self.invoice, amount=Decimal("125.00"), method="cash",
            reference="FEE-SECRET-REF", received_by=self.admin,
        )
        other_structure = FeeStructure.objects.create(
            school=self.other_school, academic_year=self.other_year,
            name="Other Tuition", amount=Decimal("9000.00"),
        )
        StudentFee.objects.create(
            student=self.other_student, fee_structure=other_structure,
            amount_due=Decimal("9000.00"),
        )
        self.fee_log = MarkAuditLog.objects.create(
            school=self.school, user=self.admin, action="fee_payment",
            details={"amount": "125.00", "payment_id": self.payment.id},
        )
        self.other_fee_log = MarkAuditLog.objects.create(
            school=self.other_school, user=self.other_admin, action="fee_assigned",
            details={"amount_due": "9000.00"},
        )
        self.mark_log = MarkAuditLog.objects.create(
            school=self.school, user=self.admin, action="publish",
            details={"exam": 1},
        )

    @staticmethod
    def _user(username):
        return User.objects.create_user(username, password="pass12345")

    def _get(self, user, url):
        self.client.force_authenticate(user)
        return self.client.get(url)

    def test_dashboard_fee_block_is_only_for_same_school_admin_or_bursar(self):
        admin = self._get(self.admin, "/api/dashboard/")
        self.assertEqual(admin.status_code, 200)
        self.assertEqual(admin.json()["fees"]["amount_due"], "500")
        self.assertEqual(admin.json()["fees"]["recent_payments"][0]["reference"], "FEE-SECRET-REF")

        bursar = self._get(self.bursar, "/api/dashboard/")
        self.assertEqual(bursar.status_code, 200)
        self.assertEqual(bursar.json()["fees"]["amount_due"], "500")
        self.assertNotIn("students", bursar.json())

        for user in (self.deputy, self.teacher):
            response = self._get(user, "/api/dashboard/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("fees", response.json())
        for user in (self.secretary, self.parent):
            self.assertEqual(self._get(user, "/api/dashboard/").status_code, 403)

        other = self._get(self.other_admin, "/api/dashboard/")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.json()["fees"]["amount_due"], "9000")
        self.assertNotEqual(other.json()["fees"]["amount_due"], "500")
        root = self._get(self.superuser, "/api/dashboard/")
        self.assertEqual(root.status_code, 200)
        self.assertNotIn("fees", root.json())
        self.assertEqual(root.json()["role"], "superadmin")

    def test_advanced_report_finance_is_scoped_and_bursar_gets_finance_only(self):
        admin = self._get(self.admin, f"/api/analytics/advanced/{self.term.id}/")
        self.assertEqual(admin.status_code, 200)
        self.assertEqual(admin.json()["finance"]["billed"], "500")
        self.assertIn("subjects", admin.json())

        bursar = self._get(self.bursar, f"/api/analytics/advanced/{self.term.id}/")
        self.assertEqual(bursar.status_code, 200)
        self.assertEqual(bursar.json()["finance"]["billed"], "500")
        self.assertNotIn("subjects", bursar.json())
        self.assertNotIn("students_with_finalized_marks", bursar.json())

        for user in (self.deputy, self.superuser):
            response = self._get(user, f"/api/analytics/advanced/{self.term.id}/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("finance", response.json())
            self.assertIn("subjects", response.json())
        for user in (self.teacher, self.secretary, self.parent):
            self.assertEqual(
                self._get(user, f"/api/analytics/advanced/{self.term.id}/").status_code,
                403,
            )
        outsider = self._get(self.other_admin, f"/api/analytics/advanced/{self.term.id}/")
        self.assertEqual(outsider.status_code, 404)
        self.assertNotIn("finance", outsider.json())

    def test_student_center_fee_fields_are_redacted_without_blocking_other_records(self):
        url = f"/api/students/{self.student.id}/center/"
        admin = self._get(self.admin, url)
        self.assertEqual(admin.status_code, 200)
        self.assertEqual(admin.json()["fee_totals"]["balance"], "375")
        self.assertEqual(admin.json()["payments"][0]["reference"], "FEE-SECRET-REF")

        bursar = self._get(self.bursar, url)
        self.assertEqual(bursar.status_code, 200)
        self.assertEqual(bursar.json()["fee_totals"]["balance"], "375")
        self.assertNotIn("history", bursar.json())
        self.assertNotIn("attendance", bursar.json())

        for user in (self.deputy, self.teacher, self.superuser):
            response = self._get(user, url)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("fees", response.json())
            self.assertNotIn("payments", response.json())
            self.assertNotIn("fee_totals", response.json())
            self.assertIn("history", response.json())
        for user in (self.secretary, self.parent):
            self.assertEqual(self._get(user, url).status_code, 403)
        outsider = self._get(self.other_admin, url)
        self.assertEqual(outsider.status_code, 404)

    def test_audit_fee_rows_are_visible_only_to_same_school_fee_roles(self):
        admin = self._get(self.admin, "/api/audit-logs/")
        self.assertEqual(admin.status_code, 200)
        self.assertIn(self.fee_log.id, [row["id"] for row in admin.json()])

        bursar = self._get(self.bursar, "/api/audit-logs/")
        self.assertEqual(bursar.status_code, 200)
        self.assertEqual([row["id"] for row in bursar.json()], [self.fee_log.id])

        deputy = self._get(self.deputy, "/api/audit-logs/")
        self.assertEqual(deputy.status_code, 200)
        self.assertNotIn(self.fee_log.id, [row["id"] for row in deputy.json()])
        self.assertIn(self.mark_log.id, [row["id"] for row in deputy.json()])

        for user in (self.teacher, self.secretary, self.parent):
            self.assertEqual(self._get(user, "/api/audit-logs/").status_code, 403)

        other = self._get(self.other_admin, "/api/audit-logs/")
        self.assertEqual(other.status_code, 200)
        self.assertEqual([row["id"] for row in other.json()], [self.other_fee_log.id])
        root = self._get(self.superuser, "/api/audit-logs/")
        self.assertEqual(root.status_code, 200)
        root_ids = [row["id"] for row in root.json()]
        self.assertNotIn(self.fee_log.id, root_ids)
        self.assertNotIn(self.other_fee_log.id, root_ids)
        self.assertIn(self.mark_log.id, root_ids)
