"""Owner decision follow-up (outside Unit U4): review existing access policy for
learner routes (/api/students/ and /api/students/<pk>/), parent-owned children and
fee/receipt views (/api/parent/children/, /api/parent/children/<student_id>/fees/,
and /api/fees/payments/<pk>/receipt/),
marks (/api/performance/** and /api/levels/**), attendance (/api/attendance/), and
feedback (/api/feedback/**). This unit intentionally does not broaden or restrict
those routes, nor does it change parent own-child fee/receipt screens.
"""
import gzip
import io
import json
import os
import tempfile
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from schools.models import (
    AcademicYear,
    BackgroundJob,
    ConnectAttachment,
    ConnectChannel,
    ConnectPost,
    ConnectReport,
    FeeAdjustment,
    FeePayment,
    FeeStructure,
    MarkAuditLog,
    Notification,
    Performance,
    School,
    SchoolAdminProfile,
    Student,
    StudentFee,
    StaffProfile,
    TeacherProfile,
)


class FeePrivacySuperuserAdminBackupTests(TestCase):
    fee_denied_detail = "You do not have permission to access fee information."

    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="U4 Privacy School", code="U4-A")
        self.other_school = School.objects.create(name="U4 Other School", code="U4-B")
        self.admin_user = User.objects.create_user("u4_admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_user, school=self.school)
        self.bursar = User.objects.create_user("u4_bursar", password="pass12345")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.deputy = User.objects.create_user("u4_deputy", password="pass12345")
        SchoolAdminProfile.objects.create(
            user=self.deputy, school=self.school, is_deputy=True,
        )
        self.teacher = User.objects.create_user("u4_teacher", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.secretary = User.objects.create_user("u4_secretary", password="pass12345")
        StaffProfile.objects.create(
            user=self.secretary, school=self.school, role="secretary",
        )
        self.parent = User.objects.create_user("u4_parent", password="pass12345")
        self.other_admin = User.objects.create_user("u4_other_admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=self.other_school)
        self.root = User.objects.create_superuser(
            "u4_root", "u4-root@example.test", "pass12345",
        )
        # Even an accidentally attached school profile must not authorize a root user.
        SchoolAdminProfile.objects.create(user=self.root, school=self.school)

        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.student = Student.objects.create(
            school=self.school, first_name="Amina", last_name="U4Learner",
            admission_number="U4-STUDENT", fee_category="boarder",
        )
        self.structure = FeeStructure.objects.create(
            school=self.school, academic_year=self.year,
            name="U4-PRIVATE-FEE-STRUCTURE", amount=Decimal("12345.67"),
        )
        self.invoice = StudentFee.objects.create(
            student=self.student, fee_structure=self.structure,
            amount_due=Decimal("12345.67"), balance_brought_forward=Decimal("234.56"),
        )
        self.payment = FeePayment.objects.create(
            student_fee=self.invoice, amount=Decimal("789.01"), method="mpesa",
            reference="U4-PRIVATE-MPESA", received_by=self.bursar,
        )
        FeeAdjustment.objects.create(
            student_fee=self.invoice, old_amount_due=Decimal("12345.67"),
            new_amount_due=Decimal("12000.00"), reason="U4-PRIVATE-ADJUSTMENT",
            made_by=self.admin_user,
        )
        MarkAuditLog.objects.create(
            school=self.school, user=self.admin_user, action="fee_payment",
            details={"amount": "789.01", "reference": "U4-PRIVATE-AUDIT"},
        )
        self.mark_log = MarkAuditLog.objects.create(
            school=self.school, user=self.admin_user, action="marks_published",
            details={"exam": "U4-MARKS-RETAINED"},
        )
        Notification.objects.create(
            school=self.school, recipient=self.admin_user, kind="announcement",
            message="U4-PRIVATE-FEE-NOTIFICATION 456.78",
        )
        channel = ConnectChannel.objects.create(
            school=self.school, name="U4 community", kind="community",
        )
        self.post = ConnectPost.objects.create(
            channel=channel, author=self.admin_user,
            body="U4-PRIVATE-CONNECT-MESSAGE 654.32",
        )
        ConnectReport.objects.create(
            post=self.post, reporter=self.parent, reason="U4-PRIVATE-CONNECT-REPORT",
        )
        self.fee_job = BackgroundJob.objects.create(
            school=self.school, requested_by=self.admin_user, job_type="fee_receipts",
            payload={"amount": "333.44", "text": "U4-PRIVATE-JOB"},
        )
        self.report_job = BackgroundJob.objects.create(
            school=self.school, requested_by=self.admin_user, job_type="report_cards",
            payload={"term": "Term 1"},
        )

        # A separate school's data verifies that school exports never cross scopes.
        other_year = AcademicYear.objects.create(
            school=self.other_school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        other_student = Student.objects.create(
            school=self.other_school, first_name="Other", last_name="U4Learner",
            admission_number="U4-OTHER-STUDENT",
        )
        other_structure = FeeStructure.objects.create(
            school=self.other_school, academic_year=other_year,
            name="U4-OTHER-SCHOOL-FEE", amount=Decimal("9876.54"),
        )
        StudentFee.objects.create(
            student=other_student, fee_structure=other_structure,
            amount_due=Decimal("9876.54"),
        )

    def api_client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_platform_backup_routes_remain_superuser_only(self):
        roles = (
            self.admin_user, self.bursar, self.deputy, self.teacher,
            self.secretary, self.parent, self.other_admin,
        )
        backup, _ = __import__("api.backup", fromlist=["build_full_backup"]).build_full_backup()
        for user in roles:
            with self.subTest(user=user.username, path="full"):
                self.assertEqual(self.api_client(user).get("/api/backups/full/").status_code, 403)
            with self.subTest(user=user.username, path="status"):
                self.assertEqual(self.api_client(user).get("/api/backups/status/").status_code, 403)
            upload = SimpleUploadedFile("backup.json.gz", backup, content_type="application/gzip")
            with self.subTest(user=user.username, path="validate"):
                self.assertEqual(
                    self.api_client(user).post(
                        "/api/backups/validate/", {"file": upload}, format="multipart",
                    ).status_code,
                    403,
                )

        response = self.api_client(self.root).get("/api/backups/full/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.api_client(self.root).get("/api/backups/status/").status_code, 200)
        upload = SimpleUploadedFile("backup.json.gz", response.content, content_type="application/gzip")
        validated = self.api_client(self.root).post(
            "/api/backups/validate/", {"file": upload}, format="multipart",
        )
        self.assertEqual(validated.status_code, 200)
        self.assertTrue(validated.data["ok"], validated.data)
        self.assertNotIn("total", validated.data["meta"])
        self.assertNotIn("schools.studentfee", validated.data["meta"]["counts"])

    def test_school_export_is_same_school_non_deputy_admin_only(self):
        allowed = self.api_client(self.admin_user).get("/api/school/export/")
        self.assertEqual(allowed.status_code, 200)
        own_dump = allowed.content.decode("utf-8")
        self.assertIn("U4-PRIVATE-FEE-STRUCTURE", own_dump)
        self.assertIn("U4-PRIVATE-MPESA", own_dump)
        self.assertNotIn("U4-OTHER-SCHOOL-FEE", own_dump)

        for user in (self.bursar, self.deputy, self.teacher, self.secretary, self.parent, self.root):
            with self.subTest(user=user.username):
                response = self.api_client(user).get("/api/school/export/")
                self.assertEqual(response.status_code, 403)
                if user is self.root or user is self.deputy:
                    self.assertEqual(response.data.get("detail"), self.fee_denied_detail)

        # An administrator of another school may export only that administrator's own school.
        other = self.api_client(self.other_admin).get("/api/school/export/")
        self.assertEqual(other.status_code, 200)
        other_dump = other.content.decode("utf-8")
        self.assertIn("U4-OTHER-SCHOOL-FEE", other_dump)
        self.assertNotIn("U4-PRIVATE-FEE-STRUCTURE", other_dump)
        self.assertNotIn("U4-PRIVATE-MPESA", other_dump)

    def test_full_backup_omits_fee_models_and_selectively_redacts_other_records(self):
        from api.backup import build_full_backup, read_backup

        blob, meta = build_full_backup()
        doc, report = read_backup(blob)
        self.assertTrue(report["ok"], report)
        labels = {row["model"] for row in doc["objects"]}
        for model in (
            "schools.feestructure", "schools.studentfee", "schools.feepayment",
            "schools.feeadjustment", "schools.connectattachment",
        ):
            self.assertNotIn(model, labels)
        self.assertIn("schools.student", labels)
        self.assertIn("schools.markauditlog", labels)
        self.assertIn("schools.backgroundjob", labels)

        student_row = next(row for row in doc["objects"] if row["model"] == "schools.student")
        self.assertEqual(student_row["fields"]["admission_number"], "U4-STUDENT")
        self.assertNotIn("fee_category", student_row["fields"])
        logs = [row for row in doc["objects"] if row["model"] == "schools.markauditlog"]
        self.assertTrue(any(row["fields"]["action"] == "marks_published" for row in logs))
        self.assertFalse(any(row["fields"]["action"].startswith("fee_") for row in logs))
        jobs = [row for row in doc["objects"] if row["model"] == "schools.backgroundjob"]
        self.assertTrue(any(row["fields"]["job_type"] == "report_cards" for row in jobs))
        self.assertFalse(any(row["fields"]["job_type"] == "fee_receipts" for row in jobs))
        post = next(row for row in doc["objects"] if row["model"] == "schools.connectpost")
        self.assertNotIn("body", post["fields"])
        report_row = next(row for row in doc["objects"] if row["model"] == "schools.connectreport")
        self.assertNotIn("reason", report_row["fields"])
        notification = next(row for row in doc["objects"] if row["model"] == "schools.notification")
        self.assertNotIn("message", notification["fields"])

        serialized = json.dumps(doc)
        for secret in (
            "U4-PRIVATE-FEE-STRUCTURE", "U4-PRIVATE-MPESA", "U4-PRIVATE-ADJUSTMENT",
            "U4-PRIVATE-AUDIT", "U4-PRIVATE-FEE-NOTIFICATION", "U4-PRIVATE-CONNECT-MESSAGE",
            "U4-PRIVATE-CONNECT-REPORT", "U4-PRIVATE-JOB", "12345.67", "789.01",
        ):
            self.assertNotIn(secret, serialized)
        self.assertIn("U4-STUDENT", serialized)
        self.assertIn("U4-MARKS-RETAINED", serialized)
        self.assertEqual(meta["counts"]["schools.student"], Student.objects.count())

    def test_backup_data_command_writes_the_redacted_platform_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            call_command("backup_data", output_dir=directory, stdout=io.StringIO())
            path = os.path.join(directory, os.listdir(directory)[0])
            doc = json.loads(gzip.decompress(open(path, "rb").read()))
        labels = {row["model"] for row in doc["objects"]}
        self.assertNotIn("schools.studentfee", labels)
        self.assertNotIn("schools.feestructure", labels)
        self.assertIn("schools.student", labels)
        self.assertIn("schools.markauditlog", labels)
        self.assertNotIn("U4-PRIVATE-MPESA", json.dumps(doc))

    def test_restore_data_warns_about_intentionally_omitted_records(self):
        with tempfile.TemporaryDirectory() as directory:
            call_command("backup_data", output_dir=directory, stdout=io.StringIO())
            path = os.path.join(directory, os.listdir(directory)[0])
            output, errors = io.StringIO(), io.StringIO()
            call_command("restore_data", path, stdout=output, stderr=errors)
        self.assertIn("omits fee records", errors.getvalue())
        self.assertIn("will not restore those records", errors.getvalue())
        self.assertIn("Check only", output.getvalue())

    def test_admin_hides_fee_models_fee_fields_and_message_content(self):
        registry = admin.site._registry
        for model in (FeeStructure, StudentFee, FeePayment, FeeAdjustment, ConnectAttachment):
            with self.subTest(model=model.__name__):
                self.assertNotIn(model, registry)
        self.assertIn(School, registry)
        self.assertIn(Student, registry)
        self.assertIn(Performance, registry)

        request = SimpleNamespace(user=self.root)
        self.assertIn("fee_category", registry[Student].get_exclude(request))
        self.assertIn("body", registry[ConnectPost].get_exclude(request))
        self.assertIn("reason", registry[ConnectReport].get_exclude(request))
        self.assertIn("message", registry[Notification].get_exclude(request))

        audit_rows = registry[MarkAuditLog].get_queryset(request)
        self.assertFalse(audit_rows.filter(action__startswith="fee_").exists())
        self.assertTrue(audit_rows.filter(action="marks_published").exists())
        visible_jobs = registry[BackgroundJob].get_queryset(request)
        self.assertFalse(visible_jobs.filter(job_type="fee_receipts").exists())
        self.assertTrue(visible_jobs.filter(job_type="report_cards").exists())
