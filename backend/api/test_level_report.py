from datetime import date
import shutil
import subprocess
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.level_report import approved_rows, build_pdf
from api.level_rules import DEFAULT_LEVELS, create_scale, move, save_level
from api.report_source import DjangoConfigStore
from marian_reports.grading import make_scheme
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, School,
    SchoolAdminProfile, Stream, Student, Subject, SubjectRegistration, Term,
    PublishedReportArtifact,
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
        self.grade = g3
        self.stream = east
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

    def _pdf(self, rows, levels=DEFAULT_LEVELS, **details):
        return build_pdf("Test School", "Amani Test", "A1", "Grade 3 East",
                         "2026", "Term 1", "end", levels, rows, **details)

    def _pdf_text(self, pdf):
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext is required for PDF text assertions")
        result = subprocess.run(
            ["pdftotext", "-", "-"], input=pdf, capture_output=True, check=True,
        )
        return result.stdout.decode("utf-8", "replace")

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

    def test_cbc_stage_layouts_are_distinct_and_senior_identity_is_present(self):
        rows = [SimpleNamespace(subject=SimpleNamespace(name="Mathematics"),
                                level_key="meets", comment="Use the recorded evidence to plan the next activity.")]
        cases = (
            ({"is_primary": True}, "PRIMARY LEARNING JOURNEY"),
            ({"is_junior": True}, "JUNIOR LEARNING PROFILE"),
            ({"is_senior": True, "pathway": "STEM", "combination": ("Mathematics", "Physics")},
             "SENIOR PATHWAY PROGRESS"),
        )
        for options, heading in cases:
            with self.subTest(stage=heading):
                text = self._pdf_text(self._pdf(
                    rows, report_no="RPT-E77-A1", verification_token="a1b2c3d4e5f6", **options))
                self.assertIn(heading, text)
                self.assertIn("INTERNAL SCHOOL ASSESSMENT", text)
                self.assertIn("NOT AN OFFICIAL KNEC", text)
                self.assertIn("RPT-E77-A1", text)
                self.assertIn("VERIFY a1b2c3d4e5f6", text)
                self.assertNotIn("SCORE / MAX", text)
                if options.get("is_senior"):
                    self.assertIn("STEM", text)
                    self.assertIn("Mathematics, Physics", text)

    def test_published_cbc_level_pdf_is_archived_and_immutable(self):
        exam = Exam.objects.create(
            school=self.school, name="Grade 3 End-term", term=self.term,
            assessment_type="end", class_level=self.grade, status="published",
            framework_key="cbe_primary", framework_version=1)
        SubjectRegistration.objects.create(
            student=self.kid, academic_year=self.year, subject=self.math,
            category="compulsory", registered_by=self.admin)
        row = self._save()
        move(self.admin, row, "submit")
        move(self.admin, row, "approve")
        DjangoConfigStore(str(self.school.pk)).save_scheme(make_scheme(
            [("Emerging", 0, 50, 1), ("Developing", 50, 70, 2),
             ("Meeting", 70, 100, 3)], pass_pct=50))

        client = APIClient()
        client.force_authenticate(self.admin)
        path = f"/api/report-module/student/{self.kid.pk}/pdf/"
        first = client.get(path, {"exam_id": str(exam.pk)})
        self.assertEqual((first.status_code, first["Content-Type"]), (200, "application/pdf"))
        artifact = PublishedReportArtifact.objects.get(exam=exam, student=self.kid)
        self.assertEqual(artifact.result_mode, "achievement_levels")
        self.assertEqual(artifact.report_no, f"RPT-E{exam.pk}-A1")
        text = self._pdf_text(first.content)
        self.assertIn("PRIMARY LEARNING JOURNEY", text)
        self.assertIn(artifact.report_no, text)
        self.assertIn("VERIFY " + artifact.verification_token, text)

        row.comment = "Changed after issue"
        row.save(update_fields=["comment", "updated_at"])
        second = client.get(path, {"exam_id": str(exam.pk)})
        self.assertEqual(second.content, first.content)
        verify = APIClient().get(
            f"/api/report-module/verify/{artifact.report_no}/",
            {"s": str(self.school.pk), "t": artifact.verification_token,
             "e": str(exam.pk)},
        )
        self.assertEqual((verify.status_code, verify.data["valid"]), (200, True))
