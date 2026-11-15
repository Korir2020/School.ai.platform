import hashlib
import hmac
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, ExamResult,
    PublishedReportArtifact, School, SchoolAdminProfile, Student,
    Subject, SubjectRegistration, Term,
)
from .models import (
    BillingConfiguration, BillingProfile, BillingTrialCycle,
    CapacityUpgradeRequest, PlatformInvoice, PlatformPayment,
)
from .services import (
    active_population, can_start_exam_cycle, price_table,
    record_analytics_generated, record_report_generated, start_trial_cycle,
)

User = get_user_model()


class BillingAuthorizationAndCommercialTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Amani School", code="AMANI")
        self.admin = User.objects.create_user(username="admin", password="test-pass")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.other_school = School.objects.create(name="Kijani School", code="KIJANI")
        self.superadmin = User.objects.create_superuser(username="root", email="root@example.test", password="test-pass")
        self.client = APIClient()

    def test_new_school_gets_trial_without_calendar_expiry(self):
        profile = BillingProfile.objects.get(school=self.school)
        self.assertEqual(profile.status, "trial_active")
        self.assertIsNotNone(profile.trial_started_at)
        self.assertIsNone(profile.trial_completed_at)

    def test_school_admin_and_superadmin_billing_privileges_are_separate(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/billing/school/").status_code, 200)
        self.assertEqual(self.client.get("/api/billing/admin/overview/").status_code, 403)
        # A client-supplied school ID cannot escape the admin's own account.
        self.assertEqual(self.client.post("/api/billing/admin/invoices/", {
            "school_id": self.other_school.pk, "kind": "annual_subscription",
        }).status_code, 403)
        self.client.force_authenticate(self.superadmin)
        self.assertEqual(self.client.get("/api/billing/admin/overview/").status_code, 200)
        self.assertEqual(self.client.get("/api/billing/school/").status_code, 403)

    def test_population_counts_unique_active_enrolled_students_only(self):
        year = AcademicYear.objects.create(school=self.school, name="2026", start_date="2026-01-01", end_date="2026-12-31", is_active=True)
        curriculum = Curriculum.objects.create(name="CBC", code="CBC-ACT", is_active=True)
        level = ClassLevel.objects.create(curriculum=curriculum, name="Grade 1", level_number=1, is_active=True)
        active = Student.objects.create(school=self.school, first_name="Ada", last_name="One", admission_number="A1", status="active")
        former = Student.objects.create(school=self.school, first_name="Bea", last_name="Two", admission_number="A2", status="left")
        Enrollment.objects.create(student=active, academic_year=year, class_level=level, is_active=True)
        Enrollment.objects.create(student=former, academic_year=year, class_level=level, is_active=True)
        count, selected_year = active_population(self.school.pk)
        self.assertEqual(count, 1)
        self.assertEqual(selected_year, year)

    def test_price_formula_and_configuration_are_owner_controlled(self):
        cfg = BillingConfiguration.objects.create(term_minimum_kes=Decimal("5000"), per_student_term_kes=Decimal("60"), terms_per_year=3, annual_discount_percent=Decimal("10"), perpetual_annual_multiplier=3, cloud_service_percent=Decimal("25"))
        prices = price_table(100, cfg)
        self.assertEqual(prices["termly_kes"], Decimal("6000.00"))
        self.assertEqual(prices["annual_kes"], Decimal("16200.00"))
        self.assertEqual(prices["perpetual_kes"], Decimal("48600.00"))
        self.assertEqual(prices["cloud_service_annual_kes"], Decimal("4050.00"))
        self.assertEqual(cfg.vat_treatment, "undecided")
        self.assertFalse(cfg.school_hosted_maintenance_approved)

    def test_school_invoice_is_server_priced_and_payment_does_not_activate_access(self):
        year = AcademicYear.objects.create(school=self.school, name="2026", start_date="2026-01-01", end_date="2026-12-31", is_active=True)
        curriculum = Curriculum.objects.create(name="CBC", code="CBC-INV", is_active=True)
        level = ClassLevel.objects.create(curriculum=curriculum, name="Grade 2", level_number=2, is_active=True)
        student = Student.objects.create(school=self.school, first_name="Ada", last_name="One", admission_number="A100")
        Enrollment.objects.create(student=student, academic_year=year, class_level=level, is_active=True)
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/billing/school/invoices/", {"kind": "annual_subscription"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        invoice = PlatformInvoice.objects.get(pk=response.data["id"])
        self.assertEqual(invoice.amount_kes, Decimal("13500.00"))
        self.assertEqual(invoice.active_student_snapshot, 1)
        response = self.client.post("/api/billing/school/bank-transfer/", {
            "invoice_id": invoice.pk, "reference": "BANK-REF-1", "idempotency_key": "bank-ref-1",
        }, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        payment = PlatformPayment.objects.get(pk=response.data["payment_id"])
        self.assertEqual(payment.status, "pending")
        self.assertEqual(BillingProfile.objects.get(school=self.school).status, "trial_active")
        duplicate = self.client.post("/api/billing/school/bank-transfer/", {
            "invoice_id": invoice.pk, "reference": "BANK-REF-1", "idempotency_key": "bank-ref-1",
        }, format="json")
        self.assertEqual(duplicate.status_code, 202)
        self.assertEqual(PlatformPayment.objects.filter(invoice=invoice).count(), 1)
        self.client.force_authenticate(self.superadmin)
        verified = self.client.post(f"/api/billing/admin/payments/{payment.pk}/review/", {
            "action": "verify", "provider_transaction_id": "BANK-CLEARED-001",
        }, format="json")
        self.assertEqual(verified.status_code, 200, verified.data)
        invoice.refresh_from_db(); payment.refresh_from_db()
        profile = BillingProfile.objects.get(school=self.school)
        self.assertEqual(payment.status, "successful")
        self.assertEqual(invoice.status, "paid")
        self.assertEqual(profile.status, "subscription_active")
        self.assertTrue(invoice.subscriptions.exists())

    def test_school_hosted_invoice_is_blocked_without_deployment_readiness(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post("/api/billing/admin/invoices/", {
            "school_id": self.school.pk, "kind": "perpetual_licence", "deployment_type": "school_hosted",
        }, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("installer", response.data["detail"])
        self.assertFalse(self.school.perpetual_licences.exists())

    def test_superadmin_manual_status_cannot_grant_unpaid_subscription(self):
        self.client.force_authenticate(self.superadmin)
        response = self.client.post(f"/api/billing/admin/schools/{self.school.pk}/profile/", {
            "status": "subscription_active", "access_type": "subscription", "note": "Manual test",
        }, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("verified paid invoice", response.data["detail"])
        self.assertEqual(BillingProfile.objects.get(school=self.school).status, "trial_active")

    def test_capacity_request_approval_does_not_charge_or_change_capacity(self):
        profile = BillingProfile.objects.get(school=self.school)
        profile.licensed_capacity = 50
        profile.save(update_fields=["licensed_capacity"])
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/billing/school/capacity-request/", {
            "requested_capacity": 100, "reason": "Growth planning",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        row = CapacityUpgradeRequest.objects.get(pk=response.data["id"])
        self.client.force_authenticate(self.superadmin)
        result = self.client.post(f"/api/billing/admin/capacity-requests/{row.pk}/decision/", {"action": "approve"}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        profile.refresh_from_db()
        self.assertEqual(profile.licensed_capacity, 50)
        self.assertEqual(PlatformInvoice.objects.filter(school=self.school).count(), 0)

    @override_settings(BILLING_WEBHOOK_SECRET="")
    def test_provider_callback_is_disabled_without_configured_secret(self):
        response = self.client.post("/api/billing/callbacks/", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertIn("not enabled", response.data["detail"])

    @override_settings(BILLING_WEBHOOK_SECRET="test-secret-long-enough-for-hmac-000000")
    def test_signed_payment_callback_is_idempotent_and_settles_exact_invoice(self):
        invoice = PlatformInvoice.objects.create(school=self.school, kind="annual_subscription", amount_kes=Decimal("5000.00"), active_student_snapshot=0, capacity_snapshot=1)
        body = json.dumps({"provider": "sandbox", "event_id": "evt-001", "invoice_number": invoice.invoice_number, "transaction_id": "txn-1", "status": "successful", "amount_kes": "5000.00", "currency": "KES", "method": "mpesa_stk"}, separators=(",", ":")).encode()
        signature = hmac.new(b"test-secret-long-enough-for-hmac-000000", body, hashlib.sha256).hexdigest()
        response = self.client.generic("POST", "/api/billing/callbacks/", body, content_type="application/json", HTTP_X_MAR_BILLING_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "paid")
        self.assertEqual(BillingProfile.objects.get(school=self.school).status, "subscription_active")
        duplicate = self.client.generic("POST", "/api/billing/callbacks/", body, content_type="application/json", HTTP_X_MAR_BILLING_SIGNATURE=signature)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.data["duplicate"])
        self.assertEqual(PlatformPayment.objects.filter(invoice=invoice).count(), 1)
        reversal_body = json.dumps({"provider": "sandbox", "event_id": "evt-002", "invoice_number": invoice.invoice_number, "transaction_id": "txn-1", "status": "reversed", "amount_kes": "5000.00", "currency": "KES", "method": "mpesa_stk"}, separators=(",", ":")).encode()
        reversal_signature = hmac.new(b"test-secret-long-enough-for-hmac-000000", reversal_body, hashlib.sha256).hexdigest()
        reversed_response = self.client.generic("POST", "/api/billing/callbacks/", reversal_body, content_type="application/json", HTTP_X_MAR_BILLING_SIGNATURE=reversal_signature)
        self.assertEqual(reversed_response.status_code, 200, reversed_response.data)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "outstanding")
        self.assertEqual(PlatformPayment.objects.get(invoice=invoice).status, "reversed")
        self.assertEqual(BillingProfile.objects.get(school=self.school).status, "payment_pending")


class GenuineTrialCycleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Cycle School", code="CYCLE")
        self.year = AcademicYear.objects.create(school=self.school, name="2026", start_date="2026-01-01", end_date="2026-12-31", is_active=True)
        self.term = Term.objects.create(academic_year=self.year, name="Term 1", start_date="2026-01-01", end_date="2026-04-30", is_active=True)
        curriculum = Curriculum.objects.create(name="CBC", code="CBC-CYCLE", is_active=True)
        self.students = []
        self.levels = []
        self.exams = []
        for index in (1, 2):
            level = ClassLevel.objects.create(curriculum=curriculum, name=f"Grade {index}", level_number=index, is_active=True)
            student = Student.objects.create(school=self.school, first_name=f"Learner{index}", last_name="Test", admission_number=f"C{index}")
            subject = Subject.objects.create(school=self.school, name=f"Subject {index}", code=f"S{index}", is_active=True)
            Enrollment.objects.create(student=student, academic_year=self.year, class_level=level, is_active=True)
            SubjectRegistration.objects.create(student=student, academic_year=self.year, subject=subject, category="compulsory")
            exam = Exam.objects.create(school=self.school, name=f"Term 1 Grade {index}", term=self.term, assessment_type="end", class_level=level, status="published")
            ExamResult.objects.create(exam=exam, student=student, overall_average=Decimal("75.00"), subject_scores={str(subject.pk): "75.00"})
            self.students.append(student); self.levels.append(level); self.exams.append(exam)
        self.cycle = start_trial_cycle(self.exams[0])

    def _archive_report(self, exam, student):
        pdf = f"test-report-{student.pk}".encode()
        PublishedReportArtifact.objects.create(
            school=self.school, exam=exam, student=student,
            report_no=f"RPT-E{exam.pk}-{student.admission_number}", result_mode="marks",
            pdf=pdf, sha256=hashlib.sha256(pdf).hexdigest(),
            source_digest="snapshot", verification_token="signedtoken",
        )

    def test_trial_does_not_complete_until_full_cohort_publication_analytics_and_archived_reports(self):
        self.assertEqual(self.cycle.expected_class_level_ids, sorted([x.pk for x in self.levels]))
        record_analytics_generated(self.exams[0])
        progress = self.cycle.__class__.objects.get(pk=self.cycle.pk)
        from .services import cycle_progress
        self.assertFalse(cycle_progress(progress)["complete"])
        for exam, student in zip(self.exams, self.students):
            record_analytics_generated(exam)
            self._archive_report(exam, student)
            record_report_generated(exam, student)
        progress = cycle_progress(self.cycle.__class__.objects.get(pk=self.cycle.pk))
        self.assertTrue(progress["complete"], progress)
        profile = BillingProfile.objects.get(school=self.school)
        self.assertEqual(profile.status, "trial_completed")
        allowed, detail = can_start_exam_cycle(self.school.pk, self.term, "mid")
        self.assertFalse(allowed)
        self.assertIn("trial", detail.lower())

    def test_publication_hook_recovers_if_exam_creation_hook_was_missed(self):
        from .services import record_exam_published
        self.cycle.delete()
        record_exam_published(self.exams[0])
        recovered = BillingTrialCycle.objects.get(school=self.school, term=self.term,
                                                  assessment_type="end")
        self.assertIn(self.levels[0].pk, recovered.expected_class_level_ids)
        self.assertTrue(recovered.evidence.filter(
            exam=self.exams[0], kind="exam_published").exists())

    def test_incomplete_or_unpublished_exam_does_not_complete_trial(self):
        self.exams[1].status = "draft"
        self.exams[1].save(update_fields=["status"])
        for exam, student in zip(self.exams, self.students):
            record_analytics_generated(exam)
            if exam.status == "published":
                self._archive_report(exam, student)
                record_report_generated(exam, student)
        from .services import cycle_progress
        progress = cycle_progress(self.cycle.__class__.objects.get(pk=self.cycle.pk))
        self.assertFalse(progress["complete"])
        self.assertEqual(BillingProfile.objects.get(school=self.school).status, "trial_active")
