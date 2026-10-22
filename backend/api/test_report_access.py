"""Tests for api/report_access.py (login -> marian_reports User)."""
import unittest
try:
    import marian_reports  # noqa: F401
except ImportError:
    raise unittest.SkipTest("marian_reports is not installed")

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from marian_reports.domain import PermissionDenied
from schools.models import (
    ClassLevel, Curriculum, GuardianProfile, School, SchoolAdminProfile,
    Stream, Student, StudentGuardian, Subject, TeacherAssignment,
    TeacherProfile,
)
from api.report_access import build_report_user


def mkuser(name):
    return get_user_model().objects.create_user(
        username=name, email=f"{name}@x.test", password="pw-12345!")


class AccessCase(TestCase):
    def setUp(self):
        cur = Curriculum.objects.create(name="CBC", code="CBC")
        mk = lambda n, k: ClassLevel.objects.create(curriculum=cur, name=n, level_number=k)
        l1, l3, l4 = mk("Form 1", 1), mk("Form 3", 3), mk("Form 4", 4)
        self.school = School.objects.create(name="Alpha", code="ALPHA", location="N", phone="0700")
        self.other = School.objects.create(name="Beta", code="BETA")
        st = lambda s, lv, n: Stream.objects.create(school=s, class_level=lv, name=n)
        self.s3, self.s4 = st(self.school, l3, "East"), st(self.school, l4, "West")
        self.so = st(self.other, l1, "North")
        sub = lambda s: Subject.objects.create(school=s, name="Maths", code="MAT")
        self.maths, self.oth_sub = sub(self.school), sub(self.other)

    def test_admin_maps_to_admin_of_own_school(self):
        u = mkuser("adm"); SchoolAdminProfile.objects.create(user=u, school=self.school)
        r = build_report_user(u)
        self.assertEqual((r.role, r.school_id, r.can_view_fees), ("admin", str(self.school.id), True))
        self.assertEqual(r.id, str(u.pk))

    def test_other_school_admin_gets_other_school(self):
        u = mkuser("adm2"); SchoolAdminProfile.objects.create(user=u, school=self.other)
        self.assertEqual(build_report_user(u).school_id, str(self.other.id))

    def test_teacher_is_denied(self):
        from marian_reports.domain import PermissionDenied
        u = mkuser("tch")
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="T1")
        with self.assertRaises(PermissionDenied):
            build_report_user(u)

    def test_guardian_gets_only_linked_students_in_own_school(self):
        u = mkuser("gua"); g = GuardianProfile.objects.create(user=u, school=self.school)
        ns = lambda s, a: Student.objects.create(school=s, first_name="A", last_name="B", admission_number=a)
        mine, _unlinked, foreign = ns(self.school, "1"), ns(self.school, "2"), ns(self.other, "3")
        StudentGuardian.objects.create(student=mine, guardian=g)
        StudentGuardian.objects.create(student=foreign, guardian=g)
        r = build_report_user(u)
        self.assertEqual((r.role, r.student_ids), ("guardian", (str(mine.id),)))

    def test_user_without_profile_is_denied(self):
        with self.assertRaises(PermissionDenied):
            build_report_user(mkuser("nobody"))

    def test_superuser_is_denied(self):
        u = mkuser("root"); u.is_superuser = True; u.save()
        with self.assertRaises(PermissionDenied):
            build_report_user(u)

    def test_anonymous_and_none_are_denied(self):
        for who in (AnonymousUser(), None):
            with self.assertRaises(PermissionDenied):
                build_report_user(who)
