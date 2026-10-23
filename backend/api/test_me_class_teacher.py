from django.test import TestCase
from rest_framework.test import APIClient

from api import test_report_views as tv
from schools.models import AcademicYear, ClassTeacher, Stream, TeacherProfile


class MeClassTeacherTests(TestCase):
    def setUp(self):
        tv.ApiCase.setUp(self)
        self.year = AcademicYear.objects.get(school=self.school)
        self.east = Stream.objects.get(school=self.school, name="East")

    def me(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c.get("/api/auth/me/")

    def test_flag_is_false_until_assigned(self):
        r = self.me(self.t3)
        self.assertEqual((r.status_code, r.data["role"], r.data["is_class_teacher"]),
                         (200, "teacher", False))

    def test_flag_is_true_for_a_class_teacher(self):
        ClassTeacher.objects.create(
            school=self.school, stream=self.east, academic_year=self.year,
            teacher=TeacherProfile.objects.get(user=self.t3))
        self.assertTrue(self.me(self.t3).data["is_class_teacher"])

    def test_admin_is_not_flagged(self):
        r = self.me(self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["is_class_teacher"])
