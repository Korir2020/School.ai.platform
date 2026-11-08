from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from api.framework_rules import FrameworkError, assign, create_version
from api.level_rules import LevelError, create_scale, save_level
from api.report_source import DjangoConfigStore
from api.report_views import service as report_service
from marian_reports.assembler import ReportService
from marian_reports.config import ReportConfig
from marian_reports.domain import User as ReportUser
from marian_reports.frameworks import get_framework
from marian_reports.grading import GradingError, make_scheme
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, CurriculumPathway, Enrollment, Exam,
    ExamResult, LevelResult, Performance, ReportSettings, School,
    SchoolAdminProfile, Stream, Student, Subject, SubjectDefinition,
    SubjectPaper, SubjectRegistration, Term,
)


class CBCSeniorBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("senior_admin", "senior@example.com", "pw12345!")
        self.school = School.objects.create(name="Senior Sample School", code="cbe-sr-test")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.curriculum = Curriculum.objects.create(name="Competency-Based Curriculum", code="CBC")
        self.grade9 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 9", level_number=9)
        self.grade10 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 10", level_number=10)
        self.grade11 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 11", level_number=11)
        self.grade12 = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 12", level_number=12)
        self.other = Curriculum.objects.create(name="Other curriculum", code="OTHER")
        self.other10 = ClassLevel.objects.create(curriculum=self.other, name="Other 10", level_number=10)
        self.stream10 = Stream.objects.create(school=self.school, class_level=self.grade10, name="East")
        self.stream9 = Stream.objects.create(school=self.school, class_level=self.grade9, name="West")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        self.stem = CurriculumPathway.objects.create(
            curriculum=self.curriculum, code="STEM", name="STEM")
        self.social = CurriculumPathway.objects.create(
            curriculum=self.curriculum, code="SOCIAL", name="Social Sciences")
        self.arts = CurriculumPathway.objects.create(
            curriculum=self.curriculum, code="ARTS", name="Arts and Sports Science")
        for path in (self.stem, self.social, self.arts):
            path.class_levels.add(self.grade10, self.grade11, self.grade12)

        self.english_def = SubjectDefinition.objects.create(
            curriculum=self.curriculum, name="English", code="S-ENG")
        self.english_def.class_levels.add(self.grade10, self.grade11, self.grade12)
        self.physics_def = SubjectDefinition.objects.create(
            curriculum=self.curriculum, name="Physics", code="S-PHY")
        self.physics_def.class_levels.add(self.grade10, self.grade11, self.grade12)
        self.physics_def.pathways.add(self.stem)
        self.history_def = SubjectDefinition.objects.create(
            curriculum=self.curriculum, name="History", code="S-HIS")
        self.history_def.class_levels.add(self.grade10, self.grade11, self.grade12)
        self.history_def.pathways.add(self.social)
        self.arts_def = SubjectDefinition.objects.create(
            curriculum=self.curriculum, name="Music and Movement", code="S-ART")
        self.arts_def.class_levels.add(self.grade10, self.grade11, self.grade12)
        self.arts_def.pathways.add(self.arts)
        self.english = Subject.objects.create(
            school=self.school, name="English", code="ENG", definition=self.english_def)
        self.physics = Subject.objects.create(
            school=self.school, name="Physics", code="PHY", definition=self.physics_def)
        self.history = Subject.objects.create(
            school=self.school, name="History", code="HIS", definition=self.history_def)
        self.arts_subject = Subject.objects.create(
            school=self.school, name="Music and Movement", code="ART", definition=self.arts_def)

        self.amani = self.learner("SEN-001", "Amani", self.stem, [self.english, self.physics])
        self.brian = self.learner("SEN-002", "Brian", self.stem, [self.english, self.physics])
        self.carey = self.learner("SEN-003", "Carey", self.social, [self.english, self.history])
        self.dara = self.learner("SEN-004", "Dara", self.arts, [self.english, self.arts_subject])

    def learner(self, admission, first, pathway, subjects, class_level=None, stream=None, year=None):
        learner = Student.objects.create(
            school=self.school, first_name=first, last_name="Learner", admission_number=admission)
        class_level = class_level or self.grade10
        year = year or self.year
        if stream is None:
            stream = self.stream10 if class_level == self.grade10 else None
        enrollment = Enrollment.objects.create(
            student=learner, academic_year=year, class_level=class_level, stream=stream,
            pathway=pathway)
        for subject in subjects:
            SubjectRegistration.objects.create(
                student=learner, academic_year=year, subject=subject, category="compulsory")
        return learner

    def senior_version(self):
        version = create_version(
            self.school, "cbe_senior", self.curriculum, 10, 12, self.admin)
        assign(self.school, version, self.admin, class_level=self.grade10, academic_year=self.year)
        return version

    def scale(self):
        return create_scale(
            self.school, self.curriculum, 10, 12, self.admin,
            levels=[
                {"key": "emerging", "label": "Emerging", "description": "Developing the school-defined skills."},
                {"key": "secure", "label": "Secure", "description": "Demonstrates the school-defined target."},
                {"key": "advanced", "label": "Advanced", "description": "Applies learning independently."},
            ],
        )

    def marks_scheme(self):
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


class CBCSeniorScopeTests(CBCSeniorBase):
    def test_framework_scale_and_no_national_defaults(self):
        with self.assertRaises(FrameworkError):
            create_version(self.school, "cbe_senior", self.curriculum, 9, 12, self.admin)
        with self.assertRaises(FrameworkError):
            create_version(self.school, "cbe_senior", self.other, 10, 12, self.admin)
        with self.assertRaises(LevelError):
            create_scale(self.school, self.curriculum, 9, 12, self.admin)
        with self.assertRaises(LevelError):
            create_scale(self.school, self.curriculum, 10, 13, self.admin)
        with self.assertRaises(GradingError):
            get_framework("cbe_senior").scheme()
        version = self.senior_version()
        self.assertEqual((version.min_level, version.max_level), (10, 12))
        self.assertEqual(self.scale().min_level, 10)

    def test_grade_and_pathway_catalogue_filters_pathway_tagged_subjects(self):
        client = self.api_client()
        response = client.get(f"/api/subject-definitions/senior/?class_level={self.grade10.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["code"] for row in response.data["pathways"]}, {"STEM", "SOCIAL", "ARTS"})
        stem = client.get(f"/api/subject-definitions/senior/?class_level={self.grade10.id}&pathway={self.stem.id}")
        self.assertEqual({row["code"] for row in stem.data["subjects"]}, {"S-ENG", "S-PHY"})
        social = client.get(f"/api/subject-definitions/senior/?class_level={self.grade10.id}&pathway={self.social.id}")
        self.assertEqual({row["code"] for row in social.data["subjects"]}, {"S-ENG", "S-HIS"})
        self.assertEqual(client.get(f"/api/subject-definitions/senior/?class_level={self.grade9.id}").status_code, 404)
        self.assertEqual(client.get(f"/api/subject-definitions/senior/?class_level={self.other10.id}").status_code, 404)

    def test_enrollment_registration_mark_and_level_entry_enforce_senior_pathway(self):
        client = self.api_client()
        no_path = client.post("/api/enrollments/", {
            "student": self.amani.id, "academic_year": self.year.id,
            "class_level": self.grade10.id, "stream": self.stream10.id,
        }, format="json")
        self.assertEqual(no_path.status_code, 400)

        wrong_registration = client.post("/api/subject-registrations/", {
            "student": self.amani.id, "academic_year": self.year.id,
            "pathway": self.social.id,
            "subjects": [{"subject": self.english.id, "category": "compulsory"},
                         {"subject": self.physics.id, "category": "compulsory"}],
        }, format="json")
        self.assertEqual(wrong_registration.status_code, 400)
        self.assertIn("selected Senior pathway", wrong_registration.data["detail"])

        SubjectRegistration.objects.create(
            student=self.carey, academic_year=self.year, subject=self.physics,
            category="optional")
        with self.assertRaisesMessage(LevelError, "not available for the selected Senior pathway"):
            save_level(self.admin, self.carey, self.physics, self.year, self.term, "mid", "secure")
        with self.assertRaisesMessage(LevelError, "not registered"):
            save_level(self.admin, self.amani, self.history, self.year, self.term, "mid", "secure")

    def test_level_scale_and_senior_level_report_are_school_authored_and_pathway_specific(self):
        self.senior_version()
        scale = self.scale()
        for learner, subjects in ((self.amani, [self.english, self.physics]),
                                  (self.brian, [self.english, self.physics]),
                                  (self.carey, [self.english, self.history]),
                                  (self.dara, [self.english, self.arts_subject])):
            for subject in subjects:
                LevelResult.objects.create(
                    student=learner, subject=subject, academic_year=self.year,
                    term=self.term, assessment_type="mid", scale=scale,
                    level_key="secure", comment="Teacher observation",
                    status="approved", entered_by=self.admin)
        exam = Exam.objects.create(
            school=self.school, name="Grade 10 Mid-term Assessment", term=self.term,
            assessment_type="mid", class_level=self.grade10)
        client = self.api_client()
        response = client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["result_mode"], "achievement_levels")
        self.assertFalse(ExamResult.objects.filter(exam=exam).exists())
        results = client.get(f"/api/exams/{exam.id}/results/")
        self.assertEqual(results.status_code, 200, results.data)
        self.assertFalse(results.data["rankings_enabled"])
        row = next(item for item in results.data["results"] if item["admission_number"] == "SEN-001")
        self.assertEqual(row["pathway_code"], "STEM")
        self.assertEqual(set(row["subject_combination"]), {"English", "Physics"})
        self.assertIn("not an official KNEC assessment", results.data["notice"])
        self.marks_scheme()
        readiness = client.get(f"/api/report-module/selection/?exam_id={exam.id}&class_name=Grade%2010")
        self.assertEqual(readiness.status_code, 200, readiness.data)
        self.assertEqual((readiness.data["selected"], readiness.data["eligible"], readiness.data["complete"]), (4, 4, 4))
        pdf = client.get(f"/api/report-module/student/{self.amani.id}/pdf/?exam_id={exam.id}")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_numeric_publication_and_reports_rank_only_within_identical_pathway_subject_sets(self):
        self.senior_version()
        self.marks_scheme()
        DjangoConfigStore(str(self.school.id)).save_sections({"positions": True, "subject_position": True})
        subject_set = {self.amani: [self.english, self.physics],
                       self.brian: [self.english, self.physics],
                       self.carey: [self.english, self.history],
                       self.dara: [self.english, self.arts_subject]}
        scores = {
            self.amani: {self.english: 80, self.physics: 80},
            self.brian: {self.english: 70, self.physics: 70},
            self.carey: {self.english: 90, self.history: 90},
            self.dara: {self.english: 60, self.arts_subject: 60},
        }
        for subject in {sub for subjects in subject_set.values() for sub in subjects}:
            SubjectPaper.objects.create(subject=subject, paper_number=1, max_marks=100, weight=100)
        for learner, subjects in scores.items():
            for subject, score in subjects.items():
                Performance.objects.create(
                    student=learner, subject=subject, academic_year=self.year, term=self.term,
                    assessment_type="end", paper_number=1, marks=score, mark_status="scored",
                    status="approved", entered_by=self.admin)
        exam = Exam.objects.create(
            school=self.school, name="Grade 10 End-term Assessment", term=self.term,
            assessment_type="end", class_level=self.grade10)
        client = self.api_client()
        published = client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(published.status_code, 200, published.data)
        self.assertTrue(published.data["rankings_enabled"],
                        (published.data, ReportSettings.objects.get(school=self.school).sections))
        results = {row.student.admission_number: row for row in ExamResult.objects.filter(
            exam=exam).select_related("student")}
        self.assertEqual(results["SEN-001"].class_rank, 1)
        self.assertEqual(results["SEN-002"].class_rank, 2)
        self.assertEqual(results["SEN-003"].class_rank, 1)
        self.assertEqual(results["SEN-004"].class_rank, 1)
        api_results = client.get(f"/api/exams/{exam.id}/results/")
        self.assertEqual(api_results.status_code, 200)
        self.assertTrue(api_results.data["rankings_enabled"])
        self.assertEqual(next(row for row in api_results.data["results"] if row["admission_number"] == "SEN-003")["pathway"], "Social Sciences")

        svc = report_service(self.school.id, exam.id)
        user = ReportUser(id=str(self.admin.id), school_id=str(self.school.id), role="admin",
                          class_names=("*",), student_ids=())
        snap = svc.snapshot(user, str(exam.id), "Grade 10")
        self.assertEqual(snap.overall.ranks[str(self.amani.id)], 1)
        self.assertEqual(snap.overall.population_sizes[str(self.amani.id)], 2)
        self.assertEqual(snap.overall.ranks[str(self.carey.id)], 1)
        self.assertEqual(snap.overall.population_sizes[str(self.carey.id)], 1)
        report = svc.build_report(user, snap, str(self.amani.id))
        self.assertEqual(report.positions["overall"]["label"], "1/2")
        insights = client.get(f"/api/report-module/analytics/?exam_id={exam.id}&class_name=Grade%2010")
        self.assertEqual(insights.status_code, 200, insights.data)
        self.assertEqual(len(insights.data["pathway_combinations"]), 3)
        ranks = client.get(f"/api/report-module/rankings/?exam_id={exam.id}&class_name=Grade%2010")
        self.assertEqual(ranks.status_code, 200, ranks.data)
        social_row = next(row for row in ranks.data["rows"] if row["adm_no"] == "SEN-003")
        self.assertEqual((social_row["position"], social_row["out_of"], social_row["pathway_code"]), (1, 1, "SOCIAL"))

    def test_year_end_promotion_requires_and_records_individual_senior_pathway(self):
        next_year = AcademicYear.objects.create(
            school=self.school, name="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31))
        learner = Student.objects.create(
            school=self.school, first_name="Eli", last_name="Nine", admission_number="SEN-009")
        Enrollment.objects.create(student=learner, academic_year=self.year,
                                  class_level=self.grade9, stream=self.stream9)
        client = self.api_client()
        preview = client.get(f"/api/promotions/preview/?from_year={self.year.id}&to_year={next_year.id}")
        self.assertEqual(preview.status_code, 200, preview.data)
        row = next(item for item in preview.data["students"] if item["student_id"] == learner.id)
        self.assertTrue(row["pathway_required"])
        self.assertEqual({item["code"] for item in row["pathways"]}, {"STEM", "SOCIAL", "ARTS"})
        missing = client.post("/api/promotions/run/", {
            "from_year": self.year.id, "to_year": next_year.id,
        }, format="json")
        self.assertEqual(missing.status_code, 409)
        self.assertTrue(Enrollment.objects.get(student=learner, academic_year=self.year).is_active)
        moved = client.post("/api/promotions/run/", {
            "from_year": self.year.id, "to_year": next_year.id,
            "pathways": {str(learner.id): self.stem.id},
        }, format="json")
        self.assertEqual(moved.status_code, 200, moved.data)
        new = Enrollment.objects.get(student=learner, academic_year=next_year)
        self.assertEqual((new.class_level_id, new.pathway_id), (self.grade10.id, self.stem.id))

    def test_senior_csv_import_requires_and_saves_pathway_code(self):
        csv_missing = b"first_name,last_name,admission_number,class_level,stream,pathway\nIvy,Import,SEN-CSV,Grade 10,East,\n"
        missing = self.api_client().post("/api/students/import/", {
            "file": SimpleUploadedFile("senior.csv", csv_missing, content_type="text/csv")
        }, format="multipart")
        self.assertEqual(missing.status_code, 200)
        self.assertFalse(missing.data["ready"])
        self.assertIn("pathway column is required", missing.data["errors"][0]["error"])

        csv_valid = b"first_name,last_name,admission_number,class_level,stream,pathway\nIvy,Import,SEN-CSV,Grade 10,East,ARTS\n"
        client = self.api_client()
        preview = client.post("/api/students/import/", {
            "file": SimpleUploadedFile("senior.csv", csv_valid, content_type="text/csv")
        }, format="multipart")
        self.assertTrue(preview.data["ready"], preview.data)
        committed = client.post("/api/students/import/", {
            "file": SimpleUploadedFile("senior.csv", csv_valid, content_type="text/csv"),
            "commit": "true",
        }, format="multipart")
        self.assertEqual(committed.status_code, 201, committed.data)
        learner = Student.objects.get(admission_number="SEN-CSV")
        enrollment = Enrollment.objects.get(student=learner, academic_year=self.year)
        self.assertEqual(enrollment.pathway_id, self.arts.id)
