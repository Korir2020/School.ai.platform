from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, Performance,
    School, SchoolAdminProfile, Stream, Student, Subject, SubjectPaper,
    SubjectRegistration, TeacherProfile, Term,
)

URL = "/api/dashboard/exams/"


class AdminExamDashboardTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", code="NORTH")
        self.other_school = School.objects.create(name="South School", code="SOUTH")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 5),
            end_date=date(2026, 4, 5),
        )
        curriculum = Curriculum.objects.create(name="Primary", code="P-EXAM-DASH")
        self.level = ClassLevel.objects.create(
            curriculum=curriculum, name="Class 5", level_number=5,
        )
        self.east = Stream.objects.create(
            school=self.school, class_level=self.level, name="East",
        )
        self.west = Stream.objects.create(
            school=self.school, class_level=self.level, name="West",
        )
        self.learner_east = Student.objects.create(
            school=self.school, first_name="Asha", last_name="Njeri",
            admission_number="N-001",
        )
        self.learner_west = Student.objects.create(
            school=self.school, first_name="Brian", last_name="Otieno",
            admission_number="N-002",
        )
        Enrollment.objects.create(
            student=self.learner_east, academic_year=self.year,
            class_level=self.level, stream=self.east,
        )
        Enrollment.objects.create(
            student=self.learner_west, academic_year=self.year,
            class_level=self.level, stream=self.west,
        )
        self.math = Subject.objects.create(school=self.school, name="Mathematics")
        self.science = Subject.objects.create(school=self.school, name="Science")
        for learner, subject in (
            (self.learner_east, self.math),
            (self.learner_east, self.science),
            (self.learner_west, self.math),
        ):
            SubjectRegistration.objects.create(
                student=learner, academic_year=self.year, subject=subject,
                category="compulsory",
            )
        SubjectPaper.objects.create(
            subject=self.math, paper_number=1, weight=Decimal("50"),
            max_marks=Decimal("100"),
        )
        SubjectPaper.objects.create(
            subject=self.math, paper_number=2, weight=Decimal("50"),
            max_marks=Decimal("100"),
        )
        # Science deliberately has no paper rows; the dashboard must apply the
        # same one-paper default as marks entry and publication.
        self.exam = Exam.objects.create(
            school=self.school, name="Term 1 Examinations", term=self.term,
            assessment_type="end", class_level=self.level,
        )
        self.teacher = User.objects.create_user("dashboard_teacher", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.admin = User.objects.create_user("dashboard_admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.other_admin = User.objects.create_user("dashboard_other_admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=self.other_school)
        self._mark(self.learner_east, self.math, 1, "0", "scored", "draft")
        self._mark(self.learner_east, self.math, 2, None, "absent", "submitted")
        self._mark(self.learner_west, self.math, 1, None, "pending", "submitted")
        self._mark(self.learner_east, self.science, 1, "80", "scored", "approved")
        # This orphan mark must not affect an unregistered learner's dashboard.
        self._mark(self.learner_west, self.science, 1, "91", "scored", "approved")

    def _mark(self, student, subject, paper, marks, disposition, workflow):
        return Performance.objects.create(
            student=student, subject=subject, academic_year=self.year,
            term=self.term, assessment_type="end", paper_number=paper,
            marks=Decimal(marks) if marks is not None else None,
            mark_status=disposition, status=workflow,
        )

    def get_dashboard(self, user=None, **params):
        if user is not None:
            self.client.force_authenticate(user)
        query = {"exam_id": self.exam.id, **params}
        return self.client.get(URL, query)

    def test_class_overview_uses_registered_subjects_and_separates_outcomes(self):
        response = self.get_dashboard(self.admin)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["exam"]["class_level"]["name"], "Class 5")
        stats = data["summary"]
        self.assertEqual(stats["enrolled_learners"], 2)
        self.assertEqual(stats["registered_learners"], 2)
        self.assertEqual(stats["expected_cells"], 5)
        self.assertEqual(stats["entered_cells"], 4)
        self.assertEqual(stats["missing_marks"], 1)
        self.assertEqual(stats["pending_approvals"], 2)
        self.assertEqual(stats["pending_dispositions"], 1)
        self.assertEqual(stats["completion_percentage"], 60.0)
        self.assertEqual(stats["average_score_pct"], 80.0)
        self.assertEqual(stats["highest_score_pct"], 80.0)
        self.assertEqual(stats["lowest_score_pct"], 80.0)
        self.assertEqual(stats["outcomes"]["scored"], 2)
        self.assertEqual(stats["outcomes"]["absent"], 1)
        self.assertEqual(stats["outcomes"]["pending"], 1)
        self.assertEqual({row["name"] for row in data["streams"]}, {"East", "West"})
        math = next(row for row in data["subjects"] if row["name"] == "Mathematics")
        self.assertEqual(math["progress"]["expected_cells"], 4)
        self.assertEqual(math["progress"]["missing_marks"], 1)

    def test_stream_subject_drilldown_returns_registered_learners_and_zero(self):
        response = self.get_dashboard(
            self.admin, stream_id=str(self.east.id), subject_id=str(self.math.id),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["expected_cells"], 2)
        self.assertEqual(data["summary"]["completion_percentage"], 100.0)
        self.assertEqual(data["summary"]["pending_approvals"], 1)
        self.assertEqual(data["learners"]["count"], 1)
        learner = data["learners"]["results"][0]
        self.assertEqual(learner["admission_number"], "N-001")
        self.assertEqual(learner["papers"][0]["mark"], "0.00")
        self.assertEqual(learner["papers"][0]["mark_status"], "scored")
        self.assertEqual(learner["papers"][1]["mark_status"], "absent")
        self.assertEqual(learner["papers"][1]["workflow_status"], "submitted")

    def test_learner_list_is_paginated(self):
        response = self.get_dashboard(
            self.admin, subject_id=str(self.math.id), page_size="1",
        )
        self.assertEqual(response.status_code, 200)
        learners = response.json()["learners"]
        self.assertEqual(learners["count"], 2)
        self.assertEqual(len(learners["results"]), 1)
        self.assertIsNotNone(learners["next"])

    def test_dashboard_rollup_query_count_is_bounded_by_roster_size(self):
        for index in range(20):
            learner = Student.objects.create(
                school=self.school, first_name=f"Learner{index}",
                last_name="Scale", admission_number=f"N-{index + 100:03d}",
            )
            Enrollment.objects.create(
                student=learner, academic_year=self.year,
                class_level=self.level, stream=self.east,
            )
            SubjectRegistration.objects.create(
                student=learner, academic_year=self.year, subject=self.math,
                category="compulsory",
            )
        self.client.force_authenticate(self.admin)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(URL, {"exam_id": self.exam.id})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 9)

    def test_school_boundary_admin_role_and_filter_validation(self):
        self.assertEqual(
            self.get_dashboard(self.other_admin).status_code, 404,
        )
        self.assertEqual(self.get_dashboard(self.teacher).status_code, 403)
        self.assertEqual(
            self.get_dashboard(self.admin, stream_id="999999").status_code, 400,
        )
        self.assertEqual(
            self.get_dashboard(self.admin, subject_id="999999").status_code, 400,
        )
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(URL).status_code, 401,
        )
