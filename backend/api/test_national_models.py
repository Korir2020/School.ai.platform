from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from schools.models import (
    AcademicYear, ClassLevel, ClassTeacher, Curriculum, School,
    Stream, Student, TeacherProfile,
)


class ClassTeacherModelTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.school = School.objects.create(name="Nat School", code="nat-test")
        user = U.objects.create_user("nat_teacher", "t@example.com", "pw12345!")
        self.tp = TeacherProfile.objects.create(user=user, school=self.school)
        cur = Curriculum.objects.create(name="Nat CBC", code="NATCBC")
        g3 = ClassLevel.objects.create(curriculum=cur, name="Grade 3", level_number=3)
        self.east = Stream.objects.create(school=self.school, class_level=g3, name="East")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))

    def _ct(self):
        return ClassTeacher.objects.create(
            school=self.school, stream=self.east, academic_year=self.year, teacher=self.tp)

    def test_one_class_teacher_per_stream_and_year(self):
        self._ct()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._ct()
