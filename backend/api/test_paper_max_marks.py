from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.serializers import ValidationError

from api.papers import SubjectPaperSerializer
from api.serializers import PerformanceSerializer
from schools.models import (
    AcademicYear, Performance, School, Student, Subject, SubjectPaper, Term,
)


class PaperMaxMarksTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Max School", code="max-test")
        self.bio = Subject.objects.create(school=self.school, name="Biology")
        self.art = Subject.objects.create(school=self.school, name="Art")
        for n, w, mx in ((1, "40", "80"), (2, "40", "80"), (3, "20", "40")):
            SubjectPaper.objects.create(
                subject=self.bio, paper_number=n, weight=Decimal(w), max_marks=Decimal(mx))
        self.kid = Student.objects.create(
            school=self.school, first_name="Amani", last_name="Test", admission_number="A1")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))

    def _check(self, subject, paper, marks):
        return PerformanceSerializer().validate(
            {"subject": subject, "paper_number": paper, "marks": Decimal(str(marks))})

    def test_default_max_is_100(self):
        sp = SubjectPaper.objects.create(subject=self.art, paper_number=1, weight=Decimal("100"))
        sp.refresh_from_db()
        self.assertEqual(sp.max_marks, Decimal("100"))

    def test_above_paper_max_refused(self):
        with self.assertRaises(ValidationError) as cm:
            self._check(self.bio, 1, 85)
        self.assertIn("marks", cm.exception.detail)
        with self.assertRaises(ValidationError):
            self._check(self.bio, 1, "80.01")

    def test_at_max_and_below_allowed(self):
        self._check(self.bio, 1, 80)
        self._check(self.bio, 1, 60)

    def test_each_paper_uses_its_own_max(self):
        with self.assertRaises(ValidationError):
            self._check(self.bio, 3, 45)
        self._check(self.bio, 3, 40)

    def test_subject_without_papers_not_restricted(self):
        self._check(self.art, 1, 99)

    def test_edit_path_uses_existing_mark(self):
        perf = Performance.objects.create(
            student=self.kid, subject=self.bio, academic_year=self.year, term=self.term,
            assessment_type="end", paper_number=1, marks=Decimal("60"))
        ser = PerformanceSerializer(perf, partial=True)
        with self.assertRaises(ValidationError):
            ser.validate({"marks": Decimal("85")})
        ser.validate({"marks": Decimal("75")})

    def test_papers_api_exposes_max_marks(self):
        sp = SubjectPaper.objects.get(subject=self.bio, paper_number=3)
        self.assertEqual(Decimal(str(SubjectPaperSerializer(sp).data["max_marks"])), Decimal("40"))
