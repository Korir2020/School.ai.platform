from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.framework_rules import (
    FrameworkError, assign, create_version, is_authorized, record_on_exam, resolve,
)
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Exam, FrameworkChangeLog, School, Term,
)


class FrameworkRulesTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.admin = U.objects.create_superuser("fw_admin", "a@example.com", "pw12345!")
        self.admin2 = U.objects.create_superuser("fw_admin2", "b@example.com", "pw12345!")
        self.plain = U.objects.create_user("fw_plain", "c@example.com", "pw12345!")
        self.school = School.objects.create(name="Test School", code="fw-test")
        self.c844 = Curriculum.objects.create(name="Test 844", code="T844")
        self.cbc = Curriculum.objects.create(name="Test CBC", code="TCBC")
        self.form1 = ClassLevel.objects.create(curriculum=self.c844, name="Form 1", level_number=1)
        self.form2 = ClassLevel.objects.create(curriculum=self.c844, name="Form 2", level_number=2)
        self.grade3 = ClassLevel.objects.create(curriculum=self.cbc, name="Grade 3", level_number=3)
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        self.v1 = create_version(self.school, "kcse_844", self.c844, 1, 4, self.admin)

    def _exam(self, level=None):
        return Exam.objects.create(
            school=self.school, name="End T1", term=self.term, class_level=level or self.form1)

    def test_not_configured_returns_none(self):
        self.assertIsNone(resolve(self.school.id, self.form1, self.year))

    def test_default_applies(self):
        assign(self.school, self.v1, self.admin)
        self.assertEqual(resolve(self.school.id, self.form1, self.year), self.v1)

    def test_override_beats_default(self):
        v2 = create_version(self.school, "kcse_844", self.c844, 1, 4, self.admin)
        assign(self.school, self.v1, self.admin)
        assign(self.school, v2, self.admin, class_level=self.form2)
        self.assertEqual(resolve(self.school.id, self.form2, self.year), v2)
        self.assertEqual(resolve(self.school.id, self.form1, self.year), self.v1)

    def test_default_ignored_where_it_does_not_cover_level(self):
        assign(self.school, self.v1, self.admin)
        self.assertIsNone(resolve(self.school.id, self.grade3, self.year))

    def test_incompatible_assignment_refused(self):
        with self.assertRaises(FrameworkError):
            assign(self.school, self.v1, self.admin, class_level=self.grade3)

    def test_unknown_framework_refused(self):
        with self.assertRaises(FrameworkError):
            create_version(self.school, "nope", self.c844, 1, 4, self.admin)

    def test_non_admin_refused(self):
        self.assertFalse(is_authorized(self.plain))
        with self.assertRaises(FrameworkError):
            assign(self.school, self.v1, self.plain)

    def test_versions_increase(self):
        v2 = create_version(self.school, "kcse_844", self.c844, 1, 4, self.admin)
        self.assertEqual((self.v1.version, v2.version), (1, 2))

    def test_publish_hook_unconfigured_does_not_block(self):
        exam = self._exam()
        self.assertIsNone(record_on_exam(exam))
        self.assertIsNone(exam.framework_key)

    def test_publish_hook_records_framework(self):
        assign(self.school, self.v1, self.admin)
        exam = self._exam()
        record_on_exam(exam)
        exam.save()
        exam.refresh_from_db()
        self.assertEqual((exam.framework_key, exam.framework_version), ("kcse_844", 1))

    def test_change_after_publish_needs_other_approver_and_keeps_old_exam(self):
        assign(self.school, self.v1, self.admin)
        exam = self._exam()
        record_on_exam(exam)
        exam.status = "published"
        exam.save()
        v2 = create_version(self.school, "kcse_844", self.c844, 1, 4, self.admin)
        with self.assertRaises(FrameworkError):
            assign(self.school, v2, self.admin)
        with self.assertRaises(FrameworkError):
            assign(self.school, v2, self.admin, approver=self.admin)
        assign(self.school, v2, self.admin, approver=self.admin2)
        exam.refresh_from_db()
        self.assertEqual(exam.framework_version, 1)
        self.assertEqual(resolve(self.school.id, self.form1, self.year), v2)
        log = FrameworkChangeLog.objects.latest("at")
        self.assertTrue(log.results_existed)
        self.assertEqual(log.approved_by, self.admin2)
