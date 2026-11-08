from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.framework_rules import FrameworkError, assign, create_version
from api.level_rules import LevelError, create_scale, roster, save_level
from api.report_source import DjangoConfigStore
from marian_reports.frameworks import get_framework, kjsea_scheme
from marian_reports.grading import make_scheme
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, ExamResult,
    LevelResult, Performance, School, SchoolAdminProfile, Stream, Student,
    Subject, SubjectDefinition, SubjectPaper, SubjectRegistration, Term,
)


class CBCJuniorBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("junior_admin", "junior@example.com", "pw12345!")
        self.school = School.objects.create(name="Junior Sample School", code="cbe-jun-test")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.curriculum = Curriculum.objects.create(name="Competency-Based Curriculum", code="CBC")
        self.grade6 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 6", level_number=6)
        self.grade7 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 7", level_number=7)
        self.grade8 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 8", level_number=8)
        self.grade9 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 9", level_number=9)
        self.grade10 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 10", level_number=10)
        self.other = Curriculum.objects.create(name="Other curriculum", code="OTHER")
        self.other7 = ClassLevel.objects.create(curriculum=self.other, name="Other Grade 7", level_number=7)
        self.stream = Stream.objects.create(school=self.school, class_level=self.grade7, name="East")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        self.amani = Student.objects.create(
            school=self.school, first_name="Amani", last_name="Otieno", admission_number="JUN-001")
        self.brian = Student.objects.create(
            school=self.school, first_name="Brian", last_name="Kamau", admission_number="JUN-002")
        for learner in (self.amani, self.brian):
            Enrollment.objects.create(
                student=learner, academic_year=self.year, class_level=self.grade7, stream=self.stream)
        self.math = Subject.objects.create(school=self.school, name="Mathematics — Grade 7", code="MATH-G7")
        self.english = Subject.objects.create(school=self.school, name="English — Grade 7", code="ENG-G7")
        for learner in (self.amani, self.brian):
            for subject in (self.math, self.english):
                SubjectRegistration.objects.create(
                    student=learner, academic_year=self.year, subject=subject, category="compulsory")

    def junior_version(self):
        version = create_version(
            self.school, "cbe_junior_levels", self.curriculum, 7, 9, self.admin)
        assign(self.school, version, self.admin, class_level=self.grade7, academic_year=self.year)
        return version

    def junior_scale(self):
        return create_scale(
            self.school, self.curriculum, 7, 9, self.admin,
            levels=[
                {"key": "beginning", "label": "Beginning", "description": "Needs further guided practice."},
                {"key": "progressing", "label": "Progressing", "description": "Applies some skills with support."},
                {"key": "meeting", "label": "Meeting", "description": "Demonstrates the school-defined target."},
                {"key": "extending", "label": "Extending", "description": "Applies learning independently in new contexts."},
            ],
        )

    def save_school_marks_scheme(self):
        scheme = make_scheme([
            ("Developing", 0, 60, 1),
            ("Meeting", 60, 75, 2),
            ("Extending", 75, 100, 3),
        ], pass_pct=60, decimals=1, rounding="half_up", mean_rule="total_over_max",
           absent_policy="pending", best_n=None)
        DjangoConfigStore(str(self.school.id)).save_scheme(scheme)
        return scheme

    def api_client(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        return client


class CBCJuniorScopeTests(CBCJuniorBase):
    def test_junior_framework_and_scale_are_confined_to_grades_7_to_9(self):
        with self.assertRaises(FrameworkError):
            create_version(self.school, "cbe_junior_levels", self.curriculum, 6, 9, self.admin)
        with self.assertRaises(FrameworkError):
            create_version(self.school, "cbe_junior_levels", self.curriculum, 7, 10, self.admin)
        with self.assertRaises(FrameworkError):
            create_version(self.school, "cbe_junior_levels", self.other, 7, 9, self.admin)
        version = create_version(self.school, "cbe_junior_levels", self.curriculum, 7, 9, self.admin)
        self.assertTrue(version.covers(self.grade8))
        with self.assertRaises(LevelError):
            create_scale(self.school, self.curriculum, 6, 9, self.admin)
        with self.assertRaises(LevelError):
            create_scale(self.school, self.curriculum, 7, 10, self.admin)
        self.assertEqual(self.junior_scale().min_level, 7)
        self.assertEqual(get_framework("cbe_junior_levels").scheme().bands, kjsea_scheme().bands)

    def test_junior_catalogue_is_limited_to_selected_cbc_grade(self):
        math = SubjectDefinition.objects.create(
            curriculum=self.curriculum, name="Mathematics", code="J-MATH")
        math.class_levels.add(self.grade7, self.grade8, self.grade9)
        science = SubjectDefinition.objects.create(
            curriculum=self.curriculum, name="Integrated Science", code="J-SCI")
        science.class_levels.add(self.grade7)
        client = self.api_client()
        response = client.get(f"/api/subject-definitions/junior/?class_level={self.grade7.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.data}, {math.id, science.id})
        response8 = client.get(f"/api/subject-definitions/junior/?class_level={self.grade8.id}")
        self.assertEqual([row["id"] for row in response8.data], [math.id])
        self.assertEqual(client.get(f"/api/subject-definitions/junior/?class_level={self.grade6.id}").status_code, 404)
        self.assertEqual(client.get(f"/api/subject-definitions/junior/?class_level={self.grade10.id}").status_code, 404)
        self.assertEqual(client.get(f"/api/subject-definitions/junior/?class_level={self.other7.id}").status_code, 404)

    def test_level_entry_requires_registration_and_roster_only_returns_registered_learners(self):
        scale = self.junior_scale()
        save_level(self.admin, self.amani, self.math, self.year, self.term, "end", "meeting")
        unregistered = Subject.objects.create(
            school=self.school, name="Unregistered", code="NO-REG")
        with self.assertRaisesMessage(LevelError, "not registered"):
            save_level(self.admin, self.amani, unregistered, self.year, self.term, "end", "meeting")
        roster_data = roster(self.admin, self.math, self.stream, self.year, self.term, "end")
        self.assertEqual({row["student_id"] for row in roster_data["rows"]}, {self.amani.id, self.brian.id})
        self.assertEqual(roster_data["levels"], scale.levels)


class CBCJuniorPublicationTests(CBCJuniorBase):
    def test_junior_descriptor_only_exam_publishes_distributions_and_report_card(self):
        self.junior_version()
        scale = self.junior_scale()
        for learner, math_key, english_key in (
            (self.amani, "meeting", "extending"),
            (self.brian, "progressing", "meeting"),
        ):
            for subject, key, comment in (
                (self.math, math_key, "Uses evidence to explain a solution."),
                (self.english, english_key, "Communicates ideas clearly."),
            ):
                LevelResult.objects.create(
                    student=learner, subject=subject, academic_year=self.year,
                    term=self.term, assessment_type="mid", scale=scale,
                    level_key=key, comment=comment, status="approved", entered_by=self.admin,
                )
        exam = Exam.objects.create(
            school=self.school, name="Grade 7 Mid-term Learning Review", term=self.term,
            assessment_type="mid", class_level=self.grade7,
        )
        client = self.api_client()
        published = client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(published.status_code, 200, published.data)
        self.assertEqual(published.data["result_mode"], "achievement_levels")
        exam.refresh_from_db()
        self.assertEqual((exam.status, exam.framework_key), ("published", "cbe_junior_levels"))
        self.assertEqual(LevelResult.objects.filter(student__in=[self.amani, self.brian], status="locked").count(), 4)
        self.assertFalse(ExamResult.objects.filter(exam=exam).exists())

        results = client.get(f"/api/exams/{exam.id}/results/")
        self.assertEqual(results.status_code, 200)
        self.assertEqual(results.data["result_mode"], "achievement_levels")
        self.assertFalse(results.data["rankings_enabled"])
        self.assertIn("not an official KNEC assessment", results.data["notice"])
        self.assertIsNone(results.data["results"][0]["overall_average"])
        self.assertIsNone(results.data["results"][0]["class_rank"])
        self.assertTrue(results.data["performance_summary"]["class"])
        self.assertTrue(results.data["performance_summary"]["streams"]["East"])

        self.save_school_marks_scheme()
        meta = client.get("/api/report-module/meta/")
        self.assertEqual(meta.status_code, 200, meta.data)
        exam_meta = next(row for row in meta.data["exams"] if row["id"] == str(exam.id))
        self.assertEqual(exam_meta["result_mode"], "achievement_levels")
        self.assertEqual(exam_meta["assessment_type"], "mid")
        self.assertFalse(exam_meta["rankings_enabled"])
        readiness = client.get(
            f"/api/report-module/selection/?exam_id={exam.id}&class_name=Grade%207")
        self.assertEqual(readiness.status_code, 200, readiness.data)
        self.assertEqual((readiness.data["selected"], readiness.data["eligible"], readiness.data["complete"]), (2, 2, 2))
        pdf = client.get(f"/api/report-module/student/{self.amani.id}/pdf/?exam_id={exam.id}")
        self.assertEqual((pdf.status_code, pdf["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        legacy = client.get(f"/api/report-card/{self.amani.id}/{self.term.id}/")
        self.assertEqual(legacy.status_code, 409)
        self.assertEqual(legacy.data["error"], "cbc_junior_report_module_required")

    def test_numeric_junior_publication_uses_school_mean_and_default_off_rankings(self):
        self.junior_version()
        self.save_school_marks_scheme()
        for subject, papers in (
            (self.math, ((1, 50, 50), (2, 100, 50))),
            (self.english, ((1, 100, 100),)),
        ):
            for number, maximum, weight in papers:
                SubjectPaper.objects.create(
                    subject=subject, paper_number=number, max_marks=maximum, weight=weight)
        marks = (
            (self.amani, self.math, 1, 40), (self.amani, self.math, 2, 60),
            (self.amani, self.english, 1, 80),
            (self.brian, self.math, 1, 30), (self.brian, self.math, 2, 70),
            (self.brian, self.english, 1, 70),
        )
        for learner, subject, paper, value in marks:
            Performance.objects.create(
                student=learner, subject=subject, academic_year=self.year,
                term=self.term, assessment_type="end", paper_number=paper,
                marks=value, mark_status="scored", status="approved", entered_by=self.admin,
            )
        exam = Exam.objects.create(
            school=self.school, name="Grade 7 Weighted School Assessment", term=self.term,
            assessment_type="end", class_level=self.grade7,
        )
        client = self.api_client()
        response = client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["rankings_enabled"])
        self.assertEqual(response.data["ranked"], 0)
        results = {row.student.admission_number: row for row in ExamResult.objects.filter(
            exam=exam).select_related("student")}
        self.assertEqual(str(results["JUN-001"].overall_average), "75.00")
        self.assertIsNone(results["JUN-001"].class_rank)
        self.assertIsNone(results["JUN-001"].stream_rank)
        published = client.get(f"/api/exams/{exam.id}/results/")
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.data["result_mode"], "marks")
        self.assertFalse(published.data["rankings_enabled"])
        self.assertIsNone(published.data["results"][0]["class_rank"])
        amani_result = next(row for row in published.data["results"]
                            if row["admission_number"] == "JUN-001")
        self.assertEqual(amani_result["overall_grade"], "Extending")
        self.assertEqual(amani_result["subject_grades"]["Mathematics — Grade 7"], "Meeting")
