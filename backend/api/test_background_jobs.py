import tempfile
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from api.background_jobs import process_one_job
from schools.models import (
    AcademicYear, BackgroundJob, FeePayment, FeeStructure, School,
    SchoolAdminProfile, StaffProfile, Student, StudentFee,
)


class BackgroundDocumentJobTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Job School", code="JOB1")
        self.other_school = School.objects.create(name="Other Job School", code="JOB2")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.student = Student.objects.create(
            school=self.school, first_name="Job", last_name="Learner",
            admission_number="J1",
        )
        self.structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.year, name="Tuition", amount="1000.00",
        )
        self.invoice = StudentFee.objects.create(
            student=self.student, fee_structure=self.structure, amount_due="1000.00",
        )
        self.payment = FeePayment.objects.create(
            student_fee=self.invoice, amount="250.00", method="cash",
        )
        self.bursar = User.objects.create_user("jobbursar", password="pass12345")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.admin = User.objects.create_user("jobadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)

    def test_worker_writes_private_artifact_and_bursar_can_download_it(self):
        with tempfile.TemporaryDirectory() as root, override_settings(
            BACKGROUND_JOB_ROOT=Path(root),
        ):
            job = BackgroundJob.objects.create(
                school=self.school, requested_by=self.bursar,
                job_type="fee_receipts", status="queued",
                payload={"payment_ids": [self.payment.id], "format": "zip"},
                total=1,
            )
            with patch("api.documents._receipt_pdf", return_value=b"pdf fixture"):
                self.assertTrue(process_one_job())

            job.refresh_from_db()
            self.assertEqual(job.status, "completed")
            self.assertEqual(job.progress, 1)
            artifact = Path(root) / str(self.school.id) / str(job.pk) / job.artifact_name
            self.assertTrue(artifact.exists())
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)

            self.client.force_authenticate(self.bursar)
            status = self.client.get(f"/api/jobs/{job.pk}/")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "completed")
            downloaded = self.client.get(f"/api/jobs/{job.pk}/download/")
            self.assertEqual(downloaded.status_code, 200)
            content = b"".join(downloaded.streaming_content)
            with zipfile.ZipFile(BytesIO(content)) as archive:
                self.assertEqual(archive.namelist(), [f"receipt-RCPT-JOB1-{self.payment.id:06d}.pdf"])
                self.assertEqual(archive.read(archive.namelist()[0]), b"pdf fixture")

    def test_job_status_and_download_are_school_scoped(self):
        foreign_user = User.objects.create_user("foreignadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=foreign_user, school=self.other_school)
        job = BackgroundJob.objects.create(
            school=self.school, requested_by=self.admin, job_type="fee_receipts",
            payload={"payment_ids": [self.payment.id], "format": "zip"}, total=1,
        )
        self.client.force_authenticate(foreign_user)
        self.assertEqual(self.client.get(f"/api/jobs/{job.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/jobs/{job.pk}/download/").status_code, 404)

    def test_document_worker_failure_is_persisted_and_queue_continues(self):
        job = BackgroundJob.objects.create(
            school=self.school, requested_by=self.bursar,
            job_type="fee_receipts", status="queued",
            payload={"payment_ids": [self.payment.id], "format": "invalid"},
            total=1,
        )
        with self.assertLogs("api.background_jobs", level="ERROR"):
            self.assertTrue(process_one_job())
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertTrue(job.error)
        self.assertTrue(process_one_job() is False)
