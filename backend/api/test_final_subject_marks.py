from datetime import date

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, ExamResult,
    FinalSubjectMark, MarkAuditLog, School, SchoolAdminProfile, Student,
    Subject, SubjectRegistration, Stream, TeacherProfile, Term,
)


class FinalSubjectMarkTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Final Marks School", code="FMS")
        self.year = AcademicYear.objects.create(school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(academic_year=self.year, name="T1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 1))
        curriculum = Curriculum.objects.create(name="CBC Final", code="CBCF")
        self.level = ClassLevel.objects.create(curriculum=curriculum, name="G7", level_number=7)
        self.stream = Stream.objects.create(school=self.school, class_level=self.level, name="A")
        self.student = Student.objects.create(school=self.school, first_name="Ann", last_name="One", admission_number="F-1")
        Enrollment.objects.create(student=self.student, academic_year=self.year, class_level=self.level, stream=self.stream)
        self.subject = Subject.objects.create(school=self.school, name="Mathematics", code="MAT")
        SubjectRegistration.objects.create(student=self.student, academic_year=self.year, subject=self.subject, category="compulsory")
        self.admin = User.objects.create_user("final_admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher = User.objects.create_user("final_teacher", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.exam = Exam.objects.create(school=self.school, name="Mid-term", term=self.term, assessment_type="mid", class_level=self.level)

    def post_final(self, user, entries=None):
        self.client.force_authenticate(user)
        return self.client.post("/api/final-subject-marks/", {
            "exam": self.exam.id, "subject": self.subject.id,
            "entries": entries or [{"student": self.student.id, "marks": 82, "mark_status": "scored"}],
        }, format="json")

    def test_only_school_admin_can_save_direct_final_mark(self):
        self.assertEqual(self.post_final(self.teacher).status_code, 403)
        response = self.post_final(self.admin)
        self.assertEqual(response.status_code, 200, response.data)
        row = FinalSubjectMark.objects.get()
        self.assertEqual((row.marks, row.status), (82, "draft"))
        self.assertEqual(MarkAuditLog.objects.filter(action="final_created").count(), 1)

    def test_final_mark_requires_registration_and_draft_exam(self):
        self.assertEqual(self.post_final(self.admin, [{"student": 99999, "marks": 70}]).status_code, 400)
        self.exam.status = "published"
        self.exam.save(update_fields=["status"])
        self.assertEqual(self.post_final(self.admin).status_code, 409)

    def test_final_mark_has_submit_approve_lock_workflow(self):
        self.post_final(self.admin)
        row = FinalSubjectMark.objects.get()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"/api/final-subject-marks/{row.id}/approve/", {"reason": "Not submitted yet"}, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"/api/final-subject-marks/{row.id}/submit/", {}, format="json").status_code, 200)
        self.assertEqual(self.client.post(f"/api/final-subject-marks/{row.id}/approve/", {"reason": "Checked against register"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(f"/api/final-subject-marks/{row.id}/lock/", {}, format="json").status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.status, "locked")

    def test_approved_final_mark_publishes_without_teacher_paper_rows(self):
        self.post_final(self.admin)
        row = FinalSubjectMark.objects.get()
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/final-subject-marks/{row.id}/submit/", {}, format="json")
        self.client.post(f"/api/final-subject-marks/{row.id}/approve/", {"reason": "Verified final subject result"}, format="json")
        response = self.client.post(f"/api/exams/{self.exam.id}/publish/")
        self.assertEqual(response.status_code, 200, response.data)
        result = ExamResult.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(result.subject_scores[self.subject.name], "82.00")
        row.refresh_from_db()
        self.assertEqual(row.status, "locked")
