from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.framework_rules import FrameworkError, assign, create_version
from api.report_source import DjangoConfigStore, DjangoDataSource
from marian_reports.assembler import ReportService
from marian_reports.config import ReportConfig
from marian_reports.domain import User as ReportUser
from marian_reports.grading import make_scheme
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, LevelResult,
    ExamResult, LevelScale, Performance, School, SchoolAdminProfile, Stream, Student,
    Subject, SubjectDefinition, SubjectPaper, SubjectRegistration, Term,
)


class CBCPrimaryBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("primary_admin", "primary@example.com", "pw12345!")
        self.school = School.objects.create(name="Primary Sample School", code="cbe-pri-test")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.curriculum = Curriculum.objects.create(name="Competency-Based Curriculum", code="CBC")
        self.grade3 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 3", level_number=3)
        self.grade4 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 4", level_number=4)
        self.grade7 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 7", level_number=7)
        self.other = Curriculum.objects.create(name="Other", code="OTHER")
        self.other1 = ClassLevel.objects.create(curriculum=self.other, name="Level 1", level_number=1)
        self.stream = Stream.objects.create(school=self.school, class_level=self.grade3, name="East")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        self.learner = Student.objects.create(
            school=self.school, first_name="Amani", last_name="Otieno", admission_number="PRI-001")
        Enrollment.objects.create(
            student=self.learner, academic_year=self.year, class_level=self.grade3, stream=self.stream)
        self.math = Subject.objects.create(school=self.school, name="Mathematics — Grade 3", code="MATH-G3")
        self.english = Subject.objects.create(school=self.school, name="English — Grade 3", code="ENG-G3")
        for subject in (self.math, self.english):
            SubjectRegistration.objects.create(
                student=self.learner, academic_year=self.year, subject=subject, category="compulsory")

    def primary_version(self):
        version = create_version(
            self.school, "cbe_primary", self.curriculum, 1, 6, self.admin)
        assign(self.school, version, self.admin, class_level=self.grade3, academic_year=self.year)
        return version

    def scale(self):
        return LevelScale.objects.create(
            school=self.school, curriculum=self.curriculum, min_level=1, max_level=6,
            version=1, created_by=self.admin,
            levels=[
                {"key": "start", "label": "Starting", "description": "Needs more guided practice."},
                {"key": "ready", "label": "Ready", "description": "Demonstrates the school-defined target."},
                {"key": "strong", "label": "Strong", "description": "Applies learning independently."},
            ],
        )


class CBCPrimaryFrameworkAndCatalogueTests(CBCPrimaryBase):
    def test_primary_framework_is_grade_and_curriculum_scoped(self):
        with self.assertRaises(FrameworkError):
            create_version(self.school, "cbe_primary", self.curriculum, 1, 7, self.admin)
        with self.assertRaises(FrameworkError):
            create_version(self.school, "cbe_primary", self.other, 1, 6, self.admin)
        version = create_version(self.school, "cbe_primary", self.curriculum, 1, 6, self.admin)
        self.assertEqual(version.framework_key, "cbe_primary")

    def test_primary_catalogue_only_returns_learning_areas_for_selected_grade(self):
        definition = SubjectDefinition.objects.create(
            curriculum=self.curriculum, name="Mathematics", code="MATH")
        definition.class_levels.add(self.grade3, self.grade4)
        definition2 = SubjectDefinition.objects.create(
            curriculum=self.curriculum, name="Grade 4 Science", code="SCI4")
        definition2.class_levels.add(self.grade4)
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get(f"/api/subject-definitions/primary/?class_level={self.grade3.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [definition.id])
        outside = client.get(f"/api/subject-definitions/primary/?class_level={self.grade7.id}")
        self.assertEqual(outside.status_code, 404)


class CBCPrimaryPublicationTests(CBCPrimaryBase):
    def test_numeric_publication_uses_school_mean_and_rankings_are_off_by_default(self):
        self.primary_version()
        configured = make_scheme([
            ("Developing", 0, 60, 1),
            ("Meeting", 60, 75, 2),
            ("Extending", 75, 100, 3),
        ], pass_pct=60, decimals=1, rounding="half_up", mean_rule="total_over_max",
           absent_policy="pending", best_n=None)
        DjangoConfigStore(str(self.school.id)).save_scheme(configured)
        SubjectPaper.objects.create(subject=self.math, paper_number=1, weight=40, max_marks=50)
        SubjectPaper.objects.create(subject=self.math, paper_number=2, weight=60, max_marks=100)
        SubjectPaper.objects.create(subject=self.english, paper_number=1, weight=100, max_marks=100)
        for subject, paper, marks in ((self.math, 1, 40), (self.math, 2, 60), (self.english, 1, 80)):
            Performance.objects.create(
                student=self.learner, subject=subject, academic_year=self.year, term=self.term,
                assessment_type="end", paper_number=paper, marks=marks,
                mark_status="scored", status="approved", entered_by=self.admin,
            )
        exam = Exam.objects.create(
            school=self.school, name="Grade 3 Weighted Assessment", term=self.term,
            assessment_type="end", class_level=self.grade3,
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["rankings_enabled"])
        self.assertEqual(response.data["ranked"], 0)
        row = ExamResult.objects.get(exam=exam, student=self.learner)
        self.assertEqual(str(row.overall_average), "74.00")
        self.assertIsNone(row.class_rank)
        self.assertIsNone(row.stream_rank)
        published = client.get(f"/api/exams/{exam.id}/results/")
        self.assertEqual(published.status_code, 200)
        self.assertFalse(published.data["rankings_enabled"])
        self.assertIsNone(published.data["results"][0]["class_rank"])

    def test_level_only_publish_locks_levels_and_returns_no_numeric_score_or_rank(self):
        self.primary_version()
        scale = self.scale()
        for subject, key in ((self.math, "ready"), (self.english, "strong")):
            LevelResult.objects.create(
                student=self.learner, subject=subject, academic_year=self.year,
                term=self.term, assessment_type="end", scale=scale,
                level_key=key, comment="Teacher note", status="approved", entered_by=self.admin,
            )
        exam = Exam.objects.create(
            school=self.school, name="Grade 3 School Assessment", term=self.term,
            assessment_type="end", class_level=self.grade3,
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        published = client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(published.status_code, 200, published.data)
        self.assertEqual(published.data["result_mode"], "achievement_levels")
        exam.refresh_from_db()
        self.assertEqual((exam.status, exam.framework_key), ("published", "cbe_primary"))
        self.assertEqual(LevelResult.objects.filter(student=self.learner, status="locked").count(), 2)
        self.assertFalse(exam.results.exists())

        result = client.get(f"/api/exams/{exam.id}/results/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["result_mode"], "achievement_levels")
        learner_result = result.data["results"][0]
        self.assertIsNone(learner_result["overall_average"])
        self.assertIsNone(learner_result["class_rank"])
        self.assertIn("Ready: 1", learner_result["overall_summary"])
        self.assertIn("not official KNEC", result.data["notice"])

        configured = make_scheme([("School result", 0, 100, 1)], pass_pct=0,
                                 decimals=1, rounding="half_up", mean_rule="total_over_max",
                                 absent_policy="pending", best_n=None)
        DjangoConfigStore(str(self.school.id)).save_scheme(configured)
        meta = client.get("/api/report-module/meta/")
        self.assertEqual(meta.status_code, 200, meta.data)
        exam_meta = next(row for row in meta.data["exams"] if row["id"] == str(exam.id))
        self.assertEqual(exam_meta["result_mode"], "achievement_levels")
        readiness = client.get(
            f"/api/report-module/selection/?exam_id={exam.id}&class_name=Grade%203")
        self.assertEqual(readiness.status_code, 200, readiness.data)
        self.assertEqual((readiness.data["eligible"], readiness.data["complete"]), (1, 1))
        pdf = client.get(
            f"/api/report-module/student/{self.learner.id}/pdf/?exam_id={exam.id}")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_level_publication_blocks_incomplete_registered_learning_areas(self):
        self.primary_version()
        scale = self.scale()
        LevelResult.objects.create(
            student=self.learner, subject=self.math, academic_year=self.year,
            term=self.term, assessment_type="end", scale=scale,
            level_key="ready", status="approved", entered_by=self.admin,
        )
        exam = Exam.objects.create(
            school=self.school, name="Incomplete Grade 3 Assessment", term=self.term,
            assessment_type="end", class_level=self.grade3,
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["count"], 1)
        exam.refresh_from_db()
        self.assertEqual(exam.status, "draft")


class CBCPrimaryWeightedReportTests(CBCPrimaryBase):
    def test_weighted_school_marks_and_approved_descriptor_render_together(self):
        scale = self.scale()
        exam = Exam.objects.create(
            school=self.school, name="Grade 3 Weighted Assessment", term=self.term,
            assessment_type="end", class_level=self.grade3,
            status="published", framework_key="cbe_primary", framework_version=1,
        )
        SubjectPaper.objects.create(subject=self.math, paper_number=1, weight=40, max_marks=50)
        SubjectPaper.objects.create(subject=self.math, paper_number=2, weight=60, max_marks=100)
        SubjectPaper.objects.create(subject=self.english, paper_number=1, weight=100, max_marks=100)
        for subject, paper, marks in ((self.math, 1, 40), (self.math, 2, 60), (self.english, 1, 80)):
            Performance.objects.create(
                student=self.learner, subject=subject, academic_year=self.year, term=self.term,
                assessment_type="end", paper_number=paper, marks=marks,
                mark_status="scored", status="approved", entered_by=self.admin,
            )
        LevelResult.objects.create(
            student=self.learner, subject=self.math, academic_year=self.year,
            term=self.term, assessment_type="end", scale=scale,
            level_key="ready", comment="Explains strategies clearly.",
            status="approved", entered_by=self.admin,
        )
        store = DjangoConfigStore(str(self.school.id))
        scheme = make_scheme([
            ("Developing", 0, 60, 1),
            ("Meeting", 60, 75, 2),
            ("Extending", 75, 100, 3),
        ], pass_pct=60, decimals=1, rounding="half_up", mean_rule="total_over_max",
           absent_policy="pending", best_n=None)
        store.save_scheme(scheme)
        service = ReportService(DjangoDataSource(), scheme, ReportConfig())
        user = ReportUser(id=str(self.admin.id), school_id=str(self.school.id), role="admin",
                          class_names=("*",), student_ids=())
        snapshot = service.snapshot(user, str(exam.id), "Grade 3")
        report = service.build_report(
            user, snapshot, str(self.learner.id))
        scores = {row.subject: row.pct for row in report.subjects}
        self.assertEqual(scores["Mathematics — Grade 3"], 68)
        self.assertEqual(scores["English — Grade 3"], 80)
        self.assertEqual(report.mean_pct, 74)
        math_row = next(row for row in report.subjects if row.subject == "Mathematics — Grade 3")
        self.assertIn("Ready", math_row.remark)
        self.assertIn("Demonstrates the school-defined target", math_row.remark)
        self.assertIn("Explains strategies clearly", math_row.remark)
        self.assertEqual(len(snapshot.students), 1)

    def test_legacy_term_report_refuses_unweighted_primary_average(self):
        exam = Exam.objects.create(
            school=self.school, name="Grade 3 Report", term=self.term,
            assessment_type="end", class_level=self.grade3,
            status="published", framework_key="cbe_primary", framework_version=1,
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get(f"/api/report-card/{self.learner.id}/{self.term.id}/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"], "cbc_primary_report_module_required")
