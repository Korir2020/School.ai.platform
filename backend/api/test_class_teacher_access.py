from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from api import test_report_views as tv
from schools.models import (
    AcademicYear, ClassTeacher, Enrollment, Stream, Student, TeacherProfile,
)


class ClassTeacherAccessTests(TestCase):
    def setUp(self):
        tv.ApiCase.setUp(self)
        self.year = AcademicYear.objects.get(school=self.school)
        self.east = Stream.objects.get(school=self.school, name="East")
        self.south = Stream.objects.create(
            school=self.school, class_level=self.level, name="South")
        self.s9 = Student.objects.create(
            school=self.school, first_name="Zed", last_name="Test", admission_number="A-9")
        Enrollment.objects.create(
            student=self.s9, academic_year=self.year, class_level=self.level, stream=self.south)
        self.tp3 = TeacherProfile.objects.get(user=self.t3)
        ClassTeacher.objects.create(
            school=self.school, stream=self.east, academic_year=self.year, teacher=self.tp3)

    def get(self, path, user=None, params=None):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        return c.get(tv.B + path, self.q if params is None else params)

    def _q(self, **extra):
        q = dict(self.q)
        q.update(extra)
        return q

    def _pdf(self, student, user, params=None):
        return self.get("student/%d/pdf/" % student.pk, user, params)

    def test_meta_lists_only_own_stream(self):
        r = self.get("meta/", self.t3)
        self.assertEqual((r.status_code, r.data["role"]), (200, "teacher"))
        self.assertEqual(sorted(s["adm_no"] for s in r.data["students"]), ["A-1", "A-2"])

    def test_opens_own_stream_pdf(self):
        r = self._pdf(self.s1, self.t3)
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_selection_defaults_to_own_stream(self):
        r = self.get("selection/", self.t3)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["selected"], 2)
        self.assertIn("East", r.data["population"])

    def test_other_stream_is_denied(self):
        self.assertEqual(self.get("selection/", self.t3, self._q(stream="South")).status_code, 403)
        self.assertEqual(self._pdf(self.s9, self.t3).status_code, 403)
        self.assertEqual(
            self.get("selection/", self.t3, self._q(ids=str(self.s9.pk))).status_code, 403)

    def test_teacher_who_is_not_class_teacher_is_denied(self):
        self.assertEqual(self.get("meta/", self.t4).status_code, 403)
        self.assertEqual(self._pdf(self.s1, self.t4).status_code, 403)
        self.assertEqual(self.get("selection/", self.t4).status_code, 403)

    def test_cannot_open_other_report_routes(self):
        for p in ("analytics/", "rankings/", "support-list/", "export/csv/", "comments/", "audit/"):
            self.assertEqual(self.get(p, self.t3).status_code, 403, p)

    def test_unpublished_exam_is_closed(self):
        self.exam.status = "draft"
        self.exam.save()
        r = self.get("meta/", self.t3)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["exams"], [])
        self.assertEqual(self.get("selection/", self.t3).status_code, 403)
        self.assertEqual(self._pdf(self.s1, self.t3).status_code, 403)

    def test_provisional_is_refused(self):
        self.assertEqual(
            self.get("selection/", self.t3, self._q(provisional="1")).status_code, 403)
        self.assertEqual(self._pdf(self.s1, self.t3, self._q(provisional="1")).status_code, 403)

    def test_class_teacher_of_another_year_is_denied_for_this_exam(self):
        y25 = AcademicYear.objects.create(
            school=self.school, name="2025", start_date=date(2025, 1, 5), end_date=date(2025, 11, 27))
        tp4 = TeacherProfile.objects.get(user=self.t4)
        ClassTeacher.objects.create(
            school=self.school, stream=self.east, academic_year=y25, teacher=tp4)
        self.assertEqual(self.get("selection/", self.t4).status_code, 403)
        self.assertEqual(self._pdf(self.s1, self.t4).status_code, 403)

    def test_admin_and_guardian_are_unchanged(self):
        r = self.get("meta/", self.admin)
        self.assertEqual((r.status_code, r.data["role"]), (200, "admin"))
        self.assertEqual(self.get("selection/", self.admin).data["selected"], 3)
        self.assertEqual(self._pdf(self.s1, self.gua).status_code, 200)
