from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import AcademicYear, FeeStructure, School, SchoolAdminProfile, Student, StudentFee, GuardianProfile, StudentGuardian, Term


class ParentPortalTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Parent School", code="PAR1")
        self.other = School.objects.create(name="Other School", code="PAR2")
        self.admin = User.objects.create_user("parentadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.parent_user = User.objects.create_user("parentone", password="pass12345")
        self.guardian = GuardianProfile.objects.create(user=self.parent_user, school=self.school)
        self.student = Student.objects.create(school=self.school, first_name="Child", last_name="One", admission_number="C1")
        self.other_student = Student.objects.create(school=self.other, first_name="Child", last_name="Two", admission_number="C2")
        StudentGuardian.objects.create(student=self.student, guardian=self.guardian)
        year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        Term.objects.create(academic_year=year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1), is_active=True)
        structure = FeeStructure.objects.create(school=self.school, academic_year=year, name="Tuition", amount=Decimal("1000.00"))
        StudentFee.objects.create(student=self.student, fee_structure=structure, amount_due=Decimal("1000.00"))

    def test_parent_sees_only_linked_children_and_fees(self):
        self.client.force_authenticate(self.parent_user)
        result = self.client.get("/api/parent/children/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()["children"]), 1)
        self.assertEqual(self.client.get(f"/api/parent/children/{self.student.id}/fees/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/parent/children/{self.other_student.id}/fees/").status_code, 404)

    def test_cross_school_guardian_link_cannot_expose_student_data(self):
        foreign_year = AcademicYear.objects.create(
            school=self.other, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        foreign_term = Term.objects.create(
            academic_year=foreign_year, name="Term 1",
            start_date=date(2026, 1, 1), end_date=date(2026, 4, 1),
        )
        foreign_structure = FeeStructure.objects.create(
            school=self.other, academic_year=foreign_year, name="Foreign tuition",
            amount=Decimal("5000.00"),
        )
        StudentFee.objects.create(
            student=self.other_student, fee_structure=foreign_structure,
            amount_due=Decimal("5000.00"),
        )
        StudentGuardian.objects.create(student=self.other_student, guardian=self.guardian)
        self.client.force_authenticate(self.parent_user)

        children = self.client.get("/api/parent/children/")
        self.assertEqual(children.status_code, 200)
        self.assertEqual([x["id"] for x in children.json()["children"]], [self.student.id])
        self.assertEqual(
            self.client.get(f"/api/parent/children/{self.other_student.id}/fees/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/report-card/{self.other_student.id}/{foreign_term.id}/"
            ).status_code,
            404,
        )

    def test_superuser_cannot_create_guardian_with_cross_school_students(self):
        root = User.objects.create_superuser(
            "rootparent", "root@example.test", "pass12345",
        )
        self.client.force_authenticate(root)
        response = self.client.post("/api/parents/", {
            "username": "mixedparent", "password": "pass12345",
            "student_ids": [self.student.id, self.other_student.id],
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_admin_can_create_parent_account(self):
        self.client.force_authenticate(self.admin)
        result = self.client.post("/api/parents/", {"username": "newparent", "password": "pass12345", "student_ids": [self.student.id]}, format="json")
        self.assertEqual(result.status_code, 201)
