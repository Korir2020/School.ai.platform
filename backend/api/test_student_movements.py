import datetime

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, School, SchoolAdminProfile,
    Stream, Student, StudentMovement, TeacherProfile)


class StudentMovementTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Hill Academy", code="HILL1")
        self.other = School.objects.create(name="Other School", code="OTH1")
        cur = Curriculum.objects.create(name="CBC")
        self.g7 = ClassLevel.objects.create(curriculum=cur, name="Grade 7", level_number=7)
        self.g8 = ClassLevel.objects.create(curriculum=cur, name="Grade 8", level_number=8)
        self.y1 = AcademicYear.objects.create(school=self.school, name="2025", start_date=datetime.date(2025, 1, 1), end_date=datetime.date(2025, 12, 1))
        self.y2 = AcademicYear.objects.create(school=self.school, name="2026", start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1))
        self.s7 = Stream.objects.create(school=self.school, class_level=self.g7, name="East")
        self.s8 = Stream.objects.create(school=self.school, class_level=self.g8, name="East")
        self.a = self._kid("A1", self.g7, self.s7)
        self.b = self._kid("B1", self.g7, self.s7)
        self.c = self._kid("C1", self.g8, self.s8)  # final class
        self.admin = User.objects.create_user("head", password="pass-12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.client.force_authenticate(self.admin)

    def _kid(self, adm, level, stream):
        st = Student.objects.create(school=self.school, first_name=adm, last_name="Kid", admission_number=adm)
        Enrollment.objects.create(student=st, academic_year=self.y1, class_level=level, stream=stream)
        return st

    def run_promo(self, **extra):
        return self.client.post("/api/promotions/run/", {"from_year": self.y1.id, "to_year": self.y2.id, **extra}, format="json")

    def test_promotion_moves_to_next_class_same_stream(self):
        r = self.run_promo()
        self.assertEqual(r.status_code, 200)
        e = Enrollment.objects.get(student=self.a, is_active=True)
        self.assertEqual((e.academic_year_id, e.class_level_id, e.stream_id), (self.y2.id, self.g8.id, self.s8.id))
        self.assertFalse(Enrollment.objects.get(student=self.a, academic_year=self.y1).is_active)

    def test_final_class_graduates(self):
        self.run_promo()
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, "graduated")
        self.assertFalse(Enrollment.objects.filter(student=self.c, is_active=True).exists())

    def test_repeat_and_skip(self):
        r = self.run_promo(repeat=[self.a.id], skip=[self.b.id])
        self.assertEqual(r.data["repeated"], 1)
        self.assertEqual(r.data["skipped"], 1)
        self.assertEqual(Enrollment.objects.get(student=self.a, is_active=True).class_level_id, self.g7.id)
        self.assertEqual(Enrollment.objects.get(student=self.b, is_active=True).academic_year_id, self.y1.id)

    def test_running_twice_does_not_double_promote(self):
        self.run_promo()
        r = self.run_promo()
        self.assertEqual(r.data["promoted"], 0)
        self.assertEqual(Enrollment.objects.filter(student=self.a).count(), 2)

    def test_new_year_must_start_later(self):
        r = self.client.post("/api/promotions/run/", {"from_year": self.y2.id, "to_year": self.y1.id}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_transfer_needs_destination_and_records_history(self):
        url = f"/api/students/{self.a.id}/exit/"
        self.assertEqual(self.client.post(url, {"kind": "transferred"}, format="json").status_code, 400)
        r = self.client.post(url, {"kind": "transferred", "destination": "Lake School"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "transferred")
        self.assertFalse(Enrollment.objects.filter(student=self.a, is_active=True).exists())
        self.assertEqual(StudentMovement.objects.get(student=self.a).from_class, "Grade 7 East")

    def test_readmit_restores_student(self):
        self.client.post(f"/api/students/{self.a.id}/exit/", {"kind": "left"}, format="json")
        r = self.client.post(f"/api/students/{self.a.id}/readmit/", {"class_level": self.g7.id, "stream": self.s7.id}, format="json")
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "active")

    def test_other_school_student_is_hidden(self):
        st = Student.objects.create(school=self.other, first_name="X", last_name="Y", admission_number="X1")
        r = self.client.post(f"/api/students/{st.id}/exit/", {"kind": "left"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_teacher_cannot_promote(self):
        t = User.objects.create_user("teach", password="pass-12345")
        TeacherProfile.objects.create(user=t, school=self.school)
        self.client.force_authenticate(t)
        self.assertEqual(self.run_promo().status_code, 403)
        self.assertEqual(self.client.post(f"/api/students/{self.a.id}/exit/", {"kind": "left"}, format="json").status_code, 403)
