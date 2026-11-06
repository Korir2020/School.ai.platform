from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import AcademicYear, FeeStructure, Performance, School, SchoolAdminProfile, Student, StudentFee, Subject, SubjectRegistration, Term


class StudentCenterTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Center School", code="CTR")
        self.other = School.objects.create(name="Other", code="OTH")
        self.admin = User.objects.create_user("centeradmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.student = Student.objects.create(school=self.school, first_name="Profile", last_name="Student", admission_number="P1")
        year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        term = Term.objects.create(academic_year=year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), is_active=True)
        subject = Subject.objects.create(school=self.school, name="Math")
        SubjectRegistration.objects.create(
            student=self.student, academic_year=year, subject=subject,
            category="compulsory")
        Performance.objects.create(student=self.student, subject=subject, academic_year=year, term=term, marks=Decimal("75"), status="approved")
        structure = FeeStructure.objects.create(school=self.school, academic_year=year, name="Tuition", amount=Decimal("500"))
        StudentFee.objects.create(student=self.student, fee_structure=structure, amount_due=Decimal("500"))

    def test_admin_can_read_complete_student_center(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/students/{self.student.id}/center/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["student"]["admission_number"], "P1")
        self.assertEqual(response.json()["history"][0]["average"], 75.0)
        self.assertEqual(response.json()["fee_totals"]["balance"], "500")

    def test_other_school_student_is_not_visible(self):
        outsider = Student.objects.create(school=self.other, first_name="Other", last_name="School", admission_number="O1")
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/students/{outsider.id}/center/").status_code, 404)
