from datetime import date
from decimal import Decimal
from io import BytesIO
import os
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from schools.models import AcademicYear, Performance, School, SchoolAdminProfile, Student, Subject, SubjectRegistration, Term


class BrandingAndAcademicReportTests(APITestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media.name)
        self.media_override.enable()
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

    def tearDown(self):
        self.media_override.disable()
        self.media.cleanup()

    @staticmethod
    def image_file(name="logo.png", image_format="PNG", content_type=None, size=(32, 32)):
        data = BytesIO()
        Image.new("RGB", size, (20, 80, 120)).save(data, format=image_format)
        return SimpleUploadedFile(
            name, data.getvalue(), content_type=content_type or {
                "PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp",
            }[image_format])

    def test_admin_can_upload_valid_logo_and_reject_large_file(self):
        self.client.force_authenticate(self.admin)
        logo = self.image_file()
        result = self.client.post("/api/school/branding/", {"logo": logo}, format="multipart")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(School.objects.get(pk=self.school.id).logo.name)
        bad = SimpleUploadedFile("logo.exe", b"bad", content_type="application/octet-stream")
        self.assertEqual(self.client.post("/api/school/branding/", {"logo": bad}, format="multipart").status_code, 400)
        oversized = SimpleUploadedFile(
            "large.png", os.urandom(2 * 1024 * 1024 + 1), content_type="image/png")
        self.assertEqual(self.client.post("/api/school/branding/", {"logo": oversized}, format="multipart").status_code, 400)

    def test_logo_rejects_spoofed_content_and_supports_replace_remove(self):
        self.client.force_authenticate(self.admin)
        spoofed = self.image_file("logo.png", "JPEG", "image/png")
        self.assertEqual(self.client.post("/api/school/branding/", {"logo": spoofed}, format="multipart").status_code, 400)
        self.assertEqual(self.client.post(
            "/api/school/branding/", {"logo": self.image_file("logo.webp", "WEBP")}, format="multipart").status_code, 200)
        self.school.refresh_from_db()
        first = self.school.logo.name
        self.assertTrue(os.path.exists(os.path.join(self.media.name, first)))
        self.assertEqual(self.client.post(
            "/api/school/branding/", {"logo": self.image_file("logo.webp", "WEBP", size=(48, 48))}, format="multipart").status_code, 200)
        self.school.refresh_from_db()
        second = self.school.logo.name
        self.assertNotEqual(first, second)
        self.assertFalse(os.path.exists(os.path.join(self.media.name, first)))
        self.assertTrue(os.path.exists(os.path.join(self.media.name, second)))
        self.assertEqual(self.client.delete("/api/school/branding/").status_code, 200)
        self.assertFalse(os.path.exists(os.path.join(self.media.name, second)))
        self.school.refresh_from_db()
        self.assertFalse(self.school.logo)

    def test_logo_isolation_uses_authenticated_school(self):
        self.client.force_authenticate(self.admin)
        self.other.logo = self.image_file("other.png")
        self.other.save(update_fields=["logo"])
        response = self.client.get(f"/api/school/branding/?school_id={self.other.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["code"], self.school.code)

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
