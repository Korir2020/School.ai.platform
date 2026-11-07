from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from schools.models import AcademicYear, Performance, School, SchoolAdminProfile, Student, Subject, SubjectRegistration, Term


class BrandingAndAcademicReportTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Brand School", code="BR1")
        self.other = School.objects.create(name="Other", code="BR2")
        self.admin = User.objects.create_user("brandadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.student = Student.objects.create(school=self.school, first_name="A", last_name="Student", admission_number="A1")
        year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(academic_year=year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), is_active=True)
        subject = Subject.objects.create(school=self.school, name="English")
        SubjectRegistration.objects.create(
            student=self.student, academic_year=year, subject=subject,
            category="compulsory")
        Performance.objects.create(student=self.student, subject=subject, academic_year=year, term=self.term, marks=Decimal("70"), status="approved")

    def test_admin_can_upload_valid_logo_and_reject_large_file(self):
        self.client.force_authenticate(self.admin)
        logo = SimpleUploadedFile("logo.png", b"fake-png", content_type="image/png")
        result = self.client.post("/api/school/branding/", {"logo": logo}, format="multipart")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(School.objects.get(pk=self.school.id).logo.name)
        bad = SimpleUploadedFile("logo.exe", b"bad", content_type="application/octet-stream")
        self.assertEqual(self.client.post("/api/school/branding/", {"logo": bad}, format="multipart").status_code, 400)

    def test_advanced_report_uses_finalized_marks_and_school_scope(self):
        self.client.force_authenticate(self.admin)
        result = self.client.get(f"/api/analytics/advanced/{self.term.id}/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["subjects"][0]["average"], 70.0)
        self.assertEqual(result.json()["students_with_finalized_marks"], 1)
        self.assertEqual(result.json()["at_risk"][0]["student_name"], "A Student")
        self.assertEqual(result.json()["pass_rate"], 100.0)
        self.assertEqual(result.json()["distribution"][4]["count"], 1)
        self.assertTrue(result.json()["trend"])
        self.assertIn("collection_rate", result.json()["finance"])
        csv_result = self.client.get(f"/api/analytics/advanced/{self.term.id}/?export=csv")
        self.assertEqual(csv_result["Content-Type"], "text/csv")
        pdf_result = self.client.get(f"/api/analytics/advanced/{self.term.id}/?export=pdf")
        self.assertEqual(pdf_result["Content-Type"], "application/pdf")
