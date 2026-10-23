from datetime import date
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.level_report import approved_rows, build_pdf
from api.level_rules import DEFAULT_LEVELS, create_scale, move, save_level
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, School, SchoolAdminProfile,
    Stream, Student, Subject, Term,
)


class LevelReportTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.school = School.objects.create(name="Rep School", code="rep-test")
        self.admin = U.objects.create_user("rep_admin", "a@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.cur = Curriculum.objects.create(name="Rep CBC", code="REPCBC")
        g3 = ClassLevel.objects.create(curriculum=self.cur, name="Grade 3", level_number=3)
        east = Stream.objects.create(school=self.school, class_level=g3, name="East")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        self.math = Subject.objects.create(school=self.school, name="Mathematics")
        self.kid = Student.objects.create(
            school=self.school, first_name="Amani", last_name="Test", admission_number="A1")
        Enrollment.objects.create(student=self.kid, academic_year=self.year, class_level=g3, stream=east)
        create_scale(self.school, self.cur, 1, 6, self.admin)

    def _save(self):
        return save_level(self.admin, self.kid, self.math, self.year, self.term, "end", "meets", "Good work")

    def _rows(self, atype="end"):
        return approved_rows(self.kid, self.year, self.term, atype)

    def test_only_approved_levels_are_printable(self):
        row = self._save()
        self.assertEqual(self._rows(), [])
        move(self.admin, row, "submit")
        self.assertEqual(self._rows(), [])
        move(self.admin, row, "approve")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].level_key, "meets")

    def test_other_assessment_type_is_not_mixed_in(self):
        row = self._save()
        move(self.admin, row, "submit")
        move(self.admin, row, "approve")
        self.assertEqual(self._rows("mid"), [])

    def _pdf(self, rows, levels=DEFAULT_LEVELS):
        return build_pdf("Test School", "Amani Test", "A1", "Grade 3 East",
                         "2026", "Term 1", "end", levels, rows)

    def test_pdf_builds_over_several_pages(self):
        rows = [SimpleNamespace(subject=SimpleNamespace(name="Subject %d" % i),
                                level_key="meets", comment="Steady progress. " * 6)
                for i in range(40)]
        pdf = self._pdf(rows)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_unknown_level_key_does_not_crash(self):
        rows = [SimpleNamespace(subject=SimpleNamespace(name="Art"), level_key="zzz", comment="")]
        self.assertTrue(self._pdf(rows).startswith(b"%PDF"))
