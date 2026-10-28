from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from api.fee_billing import apply_structure
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, FeePayment,
    FeeStructure, School, StaffProfile, Student, StudentFee,
)


class FeeBillingTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Bill School", code="BIL1")
        self.other = School.objects.create(name="Other", code="BIL2")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31))
        self.bursar = User.objects.create_user("billbursar", password="pass12345")
        StaffProfile.objects.create(user=self.bursar, school=self.school, role="bursar")
        self.client.force_authenticate(self.bursar)
        cur = Curriculum.objects.create(name="CBC", code="CBC")
        self.g3 = ClassLevel.objects.create(curriculum=cur, name="Grade 3", level_number=3)
        self.g8 = ClassLevel.objects.create(curriculum=cur, name="Grade 8", level_number=8)
        self.day3 = self.make("D3", "day", self.g3)
        self.boarder3 = self.make("B3", "boarder", self.g3)
        self.day8 = self.make("D8", "day", self.g8)
        self.outsider = Student.objects.create(
            school=self.other, first_name="O", last_name="X",
            admission_number="O1", fee_category="day")

    def make(self, adm, category, level):
        s = Student.objects.create(
            school=self.school, first_name=adm, last_name="S",
            admission_number=adm, fee_category=category)
        Enrollment.objects.create(student=s, academic_year=self.year, class_level=level)
        return s

    def post(self, **extra):
        data = {"academic_year": self.year.id, "name": "Tuition", "amount": "20000"}
        data.update(extra)
        return self.client.post("/api/fees/structures/", data, format="json")

    def billed(self):
        return set(StudentFee.objects.values_list("student__admission_number", flat=True))

    def test_everyone_bills_all_in_school_only(self):
        r = self.post()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["students_billed"], 3)
        self.assertEqual(self.billed(), {"D3", "B3", "D8"})

    def test_category_only_bills_that_category(self):
        self.post(category="boarder")
        self.assertEqual(self.billed(), {"B3"})

    def test_grade_range(self):
        self.post(from_grade=1, to_grade=6)
        self.assertEqual(self.billed(), {"D3", "B3"})

    def test_category_and_grade_together(self):
        self.post(category="day", from_grade=7, to_grade=9)
        self.assertEqual(self.billed(), {"D8"})

    def test_running_again_never_bills_twice(self):
        r = self.post()
        s = FeeStructure.objects.get(id=r.json()["id"])
        again = apply_structure(s)
        self.assertEqual(again["students_billed"], 0)
        self.assertEqual(StudentFee.objects.count(), 3)

    def test_new_amount_updates_unpaid_only(self):
        r = self.post()
        s = FeeStructure.objects.get(id=r.json()["id"])
        paid = StudentFee.objects.get(student=self.day3)
        paid.amount_paid = Decimal("500")
        paid.status = "partial"
        paid.save()
        s.amount = Decimal("25000")
        s.save()
        result = apply_structure(s)
        self.assertEqual(result["students_updated"], 2)
        self.assertEqual(StudentFee.objects.get(student=self.day3).amount_due, Decimal("20000"))
        self.assertEqual(StudentFee.objects.get(student=self.day8).amount_due, Decimal("25000"))

    def test_bad_input_is_refused(self):
        self.assertEqual(self.post(from_grade=9, to_grade=3).status_code, 400)
        self.assertEqual(self.post(category="xyz").status_code, 400)
        self.assertEqual(self.post(from_grade="abc").status_code, 400)
        self.assertEqual(StudentFee.objects.count(), 0)
