import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from api.receipt_verify import make_token
from schools.models import (
    AcademicYear, BackgroundJob, FeePayment, FeeStructure, GuardianProfile,
    School, SchoolAdminProfile, StaffProfile, Student, StudentFee,
)


class FeeReceiptDocumentPrivacyTests(APITestCase):
    denied_detail = "You do not have permission to access fee information."

    def setUp(self):
        self.school = School.objects.create(name="Receipt School", code="RCP1")
        self.other_school = School.objects.create(name="Other Receipt School", code="RCP2")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.student = Student.objects.create(
            school=self.school, first_name="Mina", last_name="Learner",
            admission_number="RCP-A1",
        )
        self.structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.year, name="Tuition",
            amount=Decimal("900.00"),
        )
        self.invoice = StudentFee.objects.create(
            student=self.student, fee_structure=self.structure,
            amount_due=Decimal("900.00"),
        )
        self.payment = FeePayment.objects.create(
            student_fee=self.invoice, amount=Decimal("125.00"), method="cash",
            reference="PRIVATE-REF",
        )
        self.admin = self._user("receipt_admin")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.bursar = self._user("receipt_bursar")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.deputy = self._user("receipt_deputy")
        SchoolAdminProfile.objects.create(
            user=self.deputy, school=self.school, is_deputy=True,
        )
        self.teacher = self._user("receipt_teacher")
        StaffProfile.objects.create(user=self.teacher, school=self.school, role="teacher")
        self.secretary = self._user("receipt_secretary")
        StaffProfile.objects.create(
            user=self.secretary, school=self.school, role="secretary",
        )
        self.parent = self._user("receipt_parent")
        GuardianProfile.objects.create(user=self.parent, school=self.school)
        self.other_admin = self._user("receipt_other_admin")
        SchoolAdminProfile.objects.create(
            user=self.other_admin, school=self.other_school,
        )
        self.superuser = User.objects.create_superuser(
            "receipt_root", "root@example.test", "pass12345",
        )

    @staticmethod
    def _user(username):
        return User.objects.create_user(username, password="pass12345")

    def _as(self, user):
        self.client.force_authenticate(user=user)

    def test_admin_and_bursar_can_list_and_export_receipts_immediately_or_queued(self):
        for user in (self.admin, self.bursar):
            with self.subTest(user=user.username):
                self._as(user)
                listed = self.client.get("/api/documents/fee-receipts/")
                self.assertEqual(listed.status_code, 200, listed.data)
                self.assertEqual(listed.data["count"], 1)
                self.assertEqual(listed.data["results"][0]["id"], self.payment.id)

                with patch("api.documents._receipt_pdf", return_value=b"pdf"), \
                        patch("api.documents._combined", return_value=b"combined-pdf"):
                    zip_response = self.client.post(
                        "/api/documents/fee-receipts/",
                        {"payment_ids": [self.payment.id], "format": "zip"},
                        format="json",
                    )
                    self.assertEqual(zip_response.status_code, 200)
                    self.assertEqual(zip_response["Content-Type"], "application/zip")
                    pdf_response = self.client.post(
                        "/api/documents/fee-receipts/",
                        {"payment_ids": [self.payment.id], "format": "combined"},
                        format="json",
                    )
                    self.assertEqual(pdf_response.status_code, 200)
                    self.assertEqual(pdf_response["Content-Type"], "application/pdf")

                with patch("api.documents.ASYNC_DOCUMENT_THRESHOLD", 1):
                    queued = self.client.post(
                        "/api/documents/fee-receipts/",
                        {"payment_ids": [self.payment.id], "format": "zip"},
                        format="json",
                    )
                self.assertEqual(queued.status_code, 202, queued.data)
                self.assertEqual(
                    BackgroundJob.objects.get(pk=queued.data["job_id"]).job_type,
                    "fee_receipts",
                )

    def test_non_fee_roles_and_superuser_cannot_list_or_export_receipts(self):
        denied = (
            self.deputy, self.teacher, self.secretary, self.parent,
            self.other_admin, self.superuser,
        )
        with patch("api.documents.ASYNC_DOCUMENT_THRESHOLD", 1):
            for user in denied:
                with self.subTest(user=user.username):
                    self._as(user)
                    calls = (
                        self.client.get(
                            "/api/documents/fee-receipts/",
                            {"school_id": self.school.id},
                        ),
                        self.client.post(
                            "/api/documents/fee-receipts/",
                            {
                                "school_id": self.school.id,
                                "payment_ids": [self.payment.id], "format": "zip",
                            },
                            format="json",
                        ),
                    )
                    for response in calls:
                        self.assertEqual(response.status_code, 403, response.data)
                        self.assertEqual(response.data.get("detail"), self.denied_detail)

    def _fee_job(self):
        return BackgroundJob.objects.create(
            school=self.school, requested_by=self.admin, job_type="fee_receipts",
            status="completed", payload={"payment_ids": [self.payment.id]},
            total=1, progress=1, artifact_name="receipts.zip",
            content_type="application/zip",
        )

    def test_admin_and_bursar_can_read_and_download_fee_receipt_jobs(self):
        job = self._fee_job()
        with tempfile.TemporaryDirectory() as root, override_settings(
            BACKGROUND_JOB_ROOT=Path(root),
        ):
            job_dir = Path(root) / str(self.school.id) / str(job.pk)
            job_dir.mkdir(parents=True)
            (job_dir / job.artifact_name).write_bytes(b"private archive")
            for user in (self.admin, self.bursar):
                with self.subTest(user=user.username):
                    self._as(user)
                    status = self.client.get(f"/api/jobs/{job.pk}/")
                    self.assertEqual(status.status_code, 200, status.data)
                    self.assertEqual(status.data["type"], "fee_receipts")
                    self.assertTrue(status.data["download_url"])
                    download = self.client.get(f"/api/jobs/{job.pk}/download/")
                    self.assertEqual(download.status_code, 200)
                    self.assertEqual(b"".join(download.streaming_content), b"private archive")

    def test_non_fee_roles_and_superuser_cannot_read_or_download_fee_receipt_jobs(self):
        job = self._fee_job()
        denied = (
            self.deputy, self.teacher, self.secretary, self.parent,
            self.other_admin, self.superuser,
        )
        for user in denied:
            with self.subTest(user=user.username):
                self._as(user)
                for suffix in ("", "download/"):
                    response = self.client.get(f"/api/jobs/{job.pk}/{suffix}")
                    self.assertEqual(response.status_code, 403, response.data)
                    self.assertEqual(response.data.get("detail"), self.denied_detail)

    def test_public_qr_check_discloses_validity_only_and_is_throttled(self):
        path = f"/api/fees/receipt-verify/{make_token(self.payment.id)}/"
        anonymous = APIClient()
        response = anonymous.get(path)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Valid receipt", content)
        for private_value in (
            "Receipt School", "RCP1", "Mina Learner", "RCP-A1", "125.00",
            "PRIVATE-REF", "Tuition", "2026",
        ):
            self.assertNotIn(private_value, content)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Robots-Tag"], "noindex")

        cache.clear()
        try:
            with patch(
                "api.receipt_verify.ReceiptVerifyThrottle.get_rate",
                return_value="1/min",
            ):
                first = anonymous.get(path)
                second = anonymous.get(path)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 429)
        finally:
            cache.clear()
