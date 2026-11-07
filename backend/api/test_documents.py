from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, BackgroundJob, FeePayment, FeeStructure, Performance, School,
    SchoolAdminProfile, Student, StudentFee, Subject, SubjectRegistration, Term,
)


class DocumentExportTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Docs School", code="DOC1", phone="0700000000")
        self.admin = User.objects.create_user("docsadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.student = Student.objects.create(school=self.school, first_name="Export", last_name="Student", admission_number="D1")
        self.year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), is_active=True)
        subject = Subject.objects.create(school=self.school, name="Mathematics")
        SubjectRegistration.objects.create(
            student=self.student, academic_year=self.year, subject=subject, category="compulsory")
        Performance.objects.create(student=self.student, subject=subject, academic_year=self.year, term=self.term, marks=Decimal("80"), status="approved")
        structure = FeeStructure.objects.create(school=self.school, academic_year=self.year, name="Tuition", amount=Decimal("1000"))
        invoice = StudentFee.objects.create(student=self.student, fee_structure=structure, amount_due=Decimal("1000"))
        self.payment = FeePayment.objects.create(student_fee=invoice, amount=Decimal("500"), method="cash", reference="CASH-1", received_by=self.admin)

    def test_preview_and_combined_report_pdf(self):
        self.client.force_authenticate(self.admin)
        preview = self.client.get(f"/api/documents/report-cards/?term_id={self.term.id}")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["eligible_count"], 1)
        pdf = self.client.post("/api/documents/report-cards/", {"term_id": self.term.id, "student_ids": [self.student.id], "format": "combined"}, format="json")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_receipt_uses_stable_payment_id_and_zip(self):
        self.client.force_authenticate(self.admin)
        preview = self.client.get("/api/documents/fee-receipts/")
        self.assertEqual(preview.json()["payments"][0]["receipt_number"], f"RCPT-DOC1-{self.payment.id:06d}")
        archive = self.client.post("/api/documents/fee-receipts/", {"payment_ids": [self.payment.id], "format": "zip"}, format="json")
        self.assertEqual(archive.status_code, 200)
        self.assertEqual(archive["Content-Type"], "application/zip")
        self.assertTrue(archive.content.startswith(b"PK"))

    def test_report_payloads_use_bounded_cohort_queries(self):
        subject = Subject.objects.get(school=self.school, name="Mathematics")
        other = Student.objects.create(
            school=self.school, first_name="Second", last_name="Export",
            admission_number="D2",
        )
        SubjectRegistration.objects.create(
            student=other, academic_year=self.year, subject=subject,
            category="compulsory",
        )
        Performance.objects.create(
            student=other, subject=subject, academic_year=self.year,
            term=self.term, marks=Decimal("60"), status="approved",
        )
        from api.documents import _report_payload, _report_payloads
        learners = [self.student, other]
        with CaptureQueriesContext(connection) as queries:
            payloads = _report_payloads(learners, self.term)
        self.assertLessEqual(len(queries), 4)
        self.assertEqual(
            payloads[self.student.id], _report_payload(self.student, self.term),
        )
        self.assertEqual(payloads[other.id], _report_payload(other, self.term))

    def test_large_report_batch_is_queued(self):
        subject = Subject.objects.get(school=self.school, name="Mathematics")
        students = [
            Student(
                school=self.school, first_name=f"Bulk{i}", last_name="Report",
                admission_number=f"BULK{i:03d}",
            ) for i in range(50)
        ]
        Student.objects.bulk_create(students)
        students = list(Student.objects.filter(admission_number__startswith="BULK"))
        SubjectRegistration.objects.bulk_create([
            SubjectRegistration(
                student=student, academic_year=self.year, subject=subject,
                category="compulsory",
            ) for student in students
        ])
        Performance.objects.bulk_create([
            Performance(
                student=student, subject=subject, academic_year=self.year,
                term=self.term, marks=Decimal("80"), status="approved",
            ) for student in students
        ])
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/documents/report-cards/", {
            "term_id": self.term.id,
            "student_ids": [student.id for student in students],
            "format": "zip",
        }, format="json")
        self.assertEqual(response.status_code, 202)
        job = BackgroundJob.objects.get(pk=response.json()["job_id"])
        self.assertEqual(job.school_id, self.school.id)
        self.assertEqual(job.job_type, "report_cards")
        self.assertEqual(job.total, 50)
