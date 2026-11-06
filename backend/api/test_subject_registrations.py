from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, ExamResult,
    Performance, School, SchoolAdminProfile, Stream, Student, Subject,
    SubjectRegistration, TeacherAssignment, TeacherProfile, Term,
)


class SubjectRegistrationTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Registration School", code="REG1")
        self.other_school = School.objects.create(name="Other School", code="REG2")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.other_year = AcademicYear.objects.create(
            school=self.other_school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 30),
        )
        curriculum = Curriculum.objects.create(name="CBC", code="REG-CBC")
        self.level = ClassLevel.objects.create(
            curriculum=curriculum, name="Grade 8", level_number=8,
        )
        self.stream = Stream.objects.create(
            school=self.school, class_level=self.level, name="East",
        )
        self.student = Student.objects.create(
            school=self.school, first_name="Amina", last_name="Learner",
            admission_number="REG-01",
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student, academic_year=self.year,
            class_level=self.level, stream=self.stream,
        )
        self.math = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        self.art = Subject.objects.create(school=self.school, name="Art", code="ART")
        self.other_subject = Subject.objects.create(
            school=self.other_school, name="Other Maths", code="OMATH",
        )
        self.admin = User.objects.create_user("regadmin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher_user = User.objects.create_user("regteacher", password="pass12345")
        teacher = TeacherProfile.objects.create(user=self.teacher_user, school=self.school)
        TeacherAssignment.objects.create(
            teacher=teacher, school=self.school, subject=self.math, stream=self.stream,
        )

    def post_registrations(self, payload, user=None):
        self.client.force_authenticate(user or self.admin)
        return self.client.post("/api/subject-registrations/", payload, format="json")

    def setUpRegs(self, subjects=None):
        if subjects is None:
            subjects = [{"subject": self.math.id, "category": "compulsory"}]
        return self.post_registrations({
            "student": self.student.id,
            "academic_year": self.year.id,
            "subjects": subjects,
        })

    def test_registers_compulsory_and_optional_individually_by_year(self):
        response = self.setUpRegs([
            {"subject": self.math.id, "category": "compulsory"},
            {"subject": self.art.id, "category": "optional"},
        ])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 2)
        rows = {row["subject"]: row["category"] for row in response.json()["registrations"]}
        self.assertEqual(rows, {self.math.id: "compulsory", self.art.id: "optional"})
        self.assertEqual(SubjectRegistration.objects.filter(
            student=self.student, academic_year=self.year).count(), 2)

    def test_replacement_changes_selection_and_category(self):
        self.setUpRegs()
        response = self.setUpRegs([
            {"subject": self.math.id, "category": "optional"},
            {"subject": self.art.id, "category": "compulsory"},
        ])
        self.assertEqual(response.status_code, 200)
        rows = {row["subject"]: row["category"] for row in response.json()["registrations"]}
        self.assertEqual(rows, {self.math.id: "optional", self.art.id: "compulsory"})
        log = self.school.mark_audit_logs.filter(action="subject_registration_updated").latest("timestamp")
        self.assertEqual(log.details["category_changed"], [self.math.id])
        self.assertEqual(log.details["added"], [self.art.id])

    def test_get_can_filter_by_learner_and_year(self):
        self.setUpRegs()
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f"/api/subject-registrations/?student={self.student.id}&academic_year={self.year.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_teacher_cannot_write_registrations(self):
        response = self.post_registrations({
            "student": self.student.id, "academic_year": self.year.id,
            "subjects": [{"subject": self.math.id, "category": "compulsory"}],
        }, user=self.teacher_user)
        self.assertEqual(response.status_code, 403)

    def test_cross_school_subject_is_rejected_without_partial_write(self):
        response = self.setUpRegs([
            {"subject": self.math.id, "category": "compulsory"},
            {"subject": self.other_subject.id, "category": "optional"},
        ])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SubjectRegistration.objects.count(), 0)

    def test_invalid_category_duplicates_and_empty_set_are_rejected(self):
        bad = self.setUpRegs([{"subject": self.math.id, "category": "elective"}])
        dup = self.setUpRegs([
            {"subject": self.math.id, "category": "compulsory"},
            {"subject": self.math.id, "category": "optional"},
        ])
        empty = self.setUpRegs([])
        self.assertEqual((bad.status_code, dup.status_code, empty.status_code), (400, 400, 400))
        self.assertEqual(SubjectRegistration.objects.count(), 0)

    def test_requires_active_enrollment_for_that_year(self):
        self.enrollment.is_active = False
        self.enrollment.save(update_fields=["is_active"])
        response = self.setUpRegs()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SubjectRegistration.objects.count(), 0)

    def test_published_exam_locks_registration_changes(self):
        self.setUpRegs()
        Exam.objects.create(
            school=self.school, name="Published", term=self.term,
            assessment_type="end", class_level=self.level, status="published",
        )
        response = self.setUpRegs([
            {"subject": self.math.id, "category": "compulsory"},
            {"subject": self.art.id, "category": "optional"},
        ])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(SubjectRegistration.objects.count(), 1)

    def test_cannot_remove_subject_with_approved_marks(self):
        self.setUpRegs([
            {"subject": self.math.id, "category": "compulsory"},
            {"subject": self.art.id, "category": "optional"},
        ])
        Performance.objects.create(
            student=self.student, subject=self.art, academic_year=self.year,
            term=self.term, assessment_type="end", marks=70, status="approved",
        )
        response = self.setUpRegs()
        self.assertEqual(response.status_code, 409)
        self.assertTrue(SubjectRegistration.objects.filter(subject=self.art).exists())

    def test_marks_entry_requires_subject_registration(self):
        self.client.force_authenticate(self.teacher_user)
        response = self.client.post("/api/performance/", {
            "student": self.student.id, "subject": self.math.id,
            "academic_year": self.year.id, "term": self.term.id,
            "assessment_type": "end", "marks": "70",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not registered", str(response.json()).lower())
        self.setUpRegs()
        accepted = self.client.post("/api/performance/", {
            "student": self.student.id, "subject": self.math.id,
            "academic_year": self.year.id, "term": self.term.id,
            "assessment_type": "end", "marks": "70",
        }, format="json")
        self.assertEqual(accepted.status_code, 201, accepted.content)

    def test_published_result_uses_only_registered_subjects(self):
        self.setUpRegs()
        unregistered = Performance.objects.create(
            student=self.student, subject=self.art, academic_year=self.year,
            term=self.term, assessment_type="end", marks=99, status="approved",
        )
        registered = Performance.objects.create(
            student=self.student, subject=self.math, academic_year=self.year,
            term=self.term, assessment_type="end", marks=70, status="approved",
        )
        exam = Exam.objects.create(
            school=self.school, name="End Term", term=self.term,
            assessment_type="end", class_level=self.level,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(response.status_code, 200, response.content)
        result = ExamResult.objects.get(exam=exam, student=self.student)
        self.assertEqual(result.overall_average, Decimal("70.00"))
        self.assertEqual(result.subject_scores, {"Mathematics": "70.00"})
        unregistered.refresh_from_db()
        registered.refresh_from_db()
        self.assertEqual(unregistered.status, "approved")
        self.assertEqual(registered.status, "locked")

    def test_absent_is_zero_for_ranking_but_is_not_a_scored_zero(self):
        self.setUpRegs()
        mark = Performance.objects.create(
            student=self.student, subject=self.math, academic_year=self.year,
            term=self.term, assessment_type="end", marks=None,
            mark_status="absent", status="approved",
        )
        exam = Exam.objects.create(
            school=self.school, name="Absence", term=self.term,
            assessment_type="end", class_level=self.level,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(response.status_code, 200, response.content)
        result = ExamResult.objects.get(exam=exam, student=self.student)
        self.assertEqual(result.overall_average, Decimal("0.00"))
        self.assertEqual(result.subject_scores, {"Mathematics": "0.00"})
        self.assertEqual(result.subject_statuses, {"Mathematics": {"1": "absent"}})
        mark.refresh_from_db()
        self.assertEqual((mark.marks, mark.mark_status, mark.status), (None, "absent", "locked"))

    def test_all_not_assessed_subjects_are_not_numeric_or_did_not_sit(self):
        self.setUpRegs()
        Performance.objects.create(
            student=self.student, subject=self.math, academic_year=self.year,
            term=self.term, assessment_type="end", marks=None,
            mark_status="not_assessed", status="approved",
        )
        exam = Exam.objects.create(
            school=self.school, name="Not assessed", term=self.term,
            assessment_type="end", class_level=self.level,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/exams/{exam.id}/publish/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["students_ranked"], 0)
        self.assertEqual(response.json()["not_ranked"][0]["subject_statuses"],
                         {"Mathematics": {"1": "not_assessed"}})
        self.assertFalse(ExamResult.objects.filter(exam=exam).exists())
        card = self.client.get(f"/api/report-card/{self.student.id}/{self.term.id}/")
        self.assertEqual(card.status_code, 200)
        self.assertEqual(card.json()["did_not_sit"], [])
        self.assertEqual(card.json()["subjects"][0]["assessments"][0]["status"],
                         "not_assessed")

    def test_term_report_card_excludes_unregistered_subjects(self):
        self.setUpRegs()
        Performance.objects.create(
            student=self.student, subject=self.math, academic_year=self.year,
            term=self.term, assessment_type="end", marks=70, status="approved",
        )
        Performance.objects.create(
            student=self.student, subject=self.art, academic_year=self.year,
            term=self.term, assessment_type="end", marks=99, status="approved",
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/report-card/{self.student.id}/{self.term.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["subject"] for row in response.json()["subjects"]], ["Mathematics"])
        self.assertEqual(response.json()["overall_average"], "70.00")
