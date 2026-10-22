from datetime import date
from importlib import import_module

from django.apps import apps
from django.test import TestCase

from schools.models import AcademicYear, ClassLevel, Curriculum, Exam, School, Term

mig = import_module("schools.migrations.0045_legacy_framework_backfill")


class LegacyBackfillTests(TestCase):
    def setUp(self):
        school = School.objects.create(name="Legacy School", code="legacy-test")
        cur = Curriculum.objects.create(name="Legacy 844", code="L844")
        self.level = ClassLevel.objects.create(curriculum=cur, name="Form 1", level_number=1)
        year = AcademicYear.objects.create(
            school=school, name="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
        self.term = Term.objects.create(
            academic_year=year, name="Term 1", start_date=date(2025, 1, 1), end_date=date(2025, 4, 30))
        self.school = school

    def _exam(self, name, atype, status, key=None, version=None):
        return Exam.objects.create(
            school=self.school, name=name, term=self.term, class_level=self.level,
            assessment_type=atype, status=status, framework_key=key, framework_version=version)

    def test_only_untracked_published_exams_are_marked(self):
        pub = self._exam("Pub", "end", "published")
        draft = self._exam("Draft", "mid", "draft")
        done = self._exam("Done", "opener", "published", key="kcse_844", version=1)
        mig.mark_legacy(apps, None)
        for e in (pub, draft, done):
            e.refresh_from_db()
        self.assertEqual(pub.framework_key, "legacy_untracked")
        self.assertIsNone(draft.framework_key)
        self.assertEqual((done.framework_key, done.framework_version), ("kcse_844", 1))

    def test_reverse_clears_only_the_legacy_label(self):
        pub = self._exam("Pub", "end", "published")
        done = self._exam("Done", "opener", "published", key="kcse_844", version=1)
        mig.mark_legacy(apps, None)
        mig.unmark_legacy(apps, None)
        pub.refresh_from_db()
        done.refresh_from_db()
        self.assertIsNone(pub.framework_key)
        self.assertEqual(done.framework_key, "kcse_844")
