from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, School,
    Performance, SchoolAdminProfile, Stream, Student, Subject, SubjectRegistration,
    TeacherAssignment,
    TeacherProfile, Term,
)


class AdminEditTests(APITestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="A1")
        self.b = School.objects.create(name="B", code="B1")
        self.admin_a = User.objects.create_user("admin_a", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_a, school=self.a)
        self.admin_b = User.objects.create_user("admin_b", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_b, school=self.b)
        self.t_user = User.objects.create_user("t_a", password="pass12345")
        self.teacher = TeacherProfile.objects.create(user=self.t_user, school=self.a)

        self.year = AcademicYear.objects.create(
            school=self.a, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="T1",
            start_date=date(2026, 1, 5), end_date=date(2026, 4, 5))
        cur = Curriculum.objects.create(name="C", code="C1")
        self.l1 = ClassLevel.objects.create(curriculum=cur, name="L1", level_number=1)
        self.l2 = ClassLevel.objects.create(curriculum=cur, name="L2", level_number=2)
        self.stream = Stream.objects.create(school=self.a, class_level=self.l1, name="East")
        self.stream_l2 = Stream.objects.create(school=self.a, class_level=self.l2, name="Top")
        self.student = Student.objects.create(
            school=self.a, first_name="Ann", last_name="A", admission_number="A-1")
        Student.objects.create(
            school=self.a, first_name="Amy", last_name="A", admission_number="A-2")
        self.subject = Subject.objects.create(school=self.a, name="Math")
        self.assign = TeacherAssignment.objects.create(
            teacher=self.teacher, school=self.a, subject=self.subject, stream=self.stream)

    def patch(self, user, url, body):
        self.client.force_authenticate(user)
        return self.client.patch(url, body, format="json")

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.patch(f"/api/students/{self.student.id}/", {}).status_code, 401)

    def test_teacher_can_read_but_not_edit(self):
        Enrollment.objects.create(
            student=self.student, academic_year=self.year,
            class_level=self.l1, stream=self.stream)
        self.client.force_authenticate(self.t_user)
        self.assertEqual(self.client.get(f"/api/students/{self.student.id}/").status_code, 200)
        r = self.patch(self.t_user, f"/api/students/{self.student.id}/", {"first_name": "X"})
        self.assertEqual(r.status_code, 403)

    def test_other_school_gets_404(self):
        for url in [f"/api/students/{self.student.id}/", f"/api/terms/{self.term.id}/",
                    f"/api/streams/{self.stream.id}/", f"/api/subjects/{self.subject.id}/",
                    f"/api/academic-years/{self.year.id}/",
                    f"/api/teacher-assignments/{self.assign.id}/"]:
            self.client.force_authenticate(self.admin_b)
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(
            self.patch(self.admin_b, f"/api/students/{self.student.id}/", {"first_name": "X"}).status_code, 404)

    def test_admin_edits_student_but_not_school(self):
        r = self.patch(self.admin_a, f"/api/students/{self.student.id}/",
                       {"first_name": "Anna", "school": self.b.id})
        self.assertEqual(r.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Anna")
        self.assertEqual(self.student.school_id, self.a.id)

    def test_empty_patch_400(self):
        r = self.patch(self.admin_a, f"/api/students/{self.student.id}/", {"school": self.b.id})
        self.assertEqual(r.status_code, 400)

    def test_duplicate_admission_number_400(self):
        r = self.patch(self.admin_a, f"/api/students/{self.student.id}/", {"admission_number": "A-2"})
        self.assertEqual(r.status_code, 400)

    def test_deactivate_stream_and_subject(self):
        self.assertEqual(self.patch(self.admin_a, f"/api/streams/{self.stream.id}/", {"is_active": False}).status_code, 200)
        self.assertEqual(self.patch(self.admin_a, f"/api/subjects/{self.subject.id}/", {"is_active": False}).status_code, 200)
        self.stream.refresh_from_db()
        self.assertFalse(self.stream.is_active)

    def test_stream_and_subject_names_are_trimmed_case_insensitive_unique(self):
        self.client.force_authenticate(self.admin_a)
        stream = self.client.post(
            "/api/streams/",
            {"class_level": self.l1.id, "name": "  east  ", "is_active": True},
            format="json",
        )
        subject = self.client.post(
            "/api/subjects/",
            {"name": " MATH ", "code": "M2", "is_active": True},
            format="json",
        )
        self.assertEqual(stream.status_code, 400, stream.data)
        self.assertEqual(subject.status_code, 400, subject.data)

    def test_edit_duplicate_name_is_rejected(self):
        self.client.force_authenticate(self.admin_a)
        response = self.client.patch(
            f"/api/streams/{self.stream_l2.id}/",
            {"name": " EAST "},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        other_subject = Subject.objects.create(school=self.a, name="Science", code="SCI")
        response = self.client.patch(
            f"/api/subjects/{other_subject.id}/",
            {"name": "  math  "},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_stream_delete_requires_preview_then_confirmation(self):
        url = f"/api/streams/{self.stream.id}/"
        self.client.force_authenticate(self.admin_a)
        preview = self.client.delete(url)
        self.assertEqual(preview.status_code, 409)
        self.assertTrue(preview.data["requires_confirmation"])
        self.assertIn("teacher_assignments_removed", preview.data["impact"])
        self.assertTrue(Stream.objects.filter(pk=self.stream.id).exists())
        deleted = self.client.delete(url, {"confirm": True}, format="json")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Stream.objects.filter(pk=self.stream.id).exists())
        self.assertFalse(TeacherAssignment.objects.filter(pk=self.assign.id).exists())

    def test_subject_delete_is_blocked_by_registrations(self):
        SubjectRegistration.objects.create(
            student=self.student, academic_year=self.year, subject=self.subject,
            category="compulsory",
        )
        self.client.force_authenticate(self.admin_a)
        response = self.client.delete(f"/api/subjects/{self.subject.id}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.data["blocked"])
        self.assertTrue(Subject.objects.filter(pk=self.subject.id).exists())

    def test_subject_delete_previews_mark_loss_until_confirmed(self):
        mark = Performance.objects.create(
            student=self.student,
            subject=self.subject,
            academic_year=self.year,
            term=self.term,
            marks=Decimal("72"),
            status="approved",
        )
        self.client.force_authenticate(self.admin_a)
        url = f"/api/subjects/{self.subject.id}/"

        preview = self.client.delete(url)
        self.assertEqual(preview.status_code, 409)
        self.assertEqual(preview.data["impact"]["learners_affected"], 1)
        self.assertEqual(preview.data["impact"]["marks_affected"], 1)
        self.assertTrue(Performance.objects.filter(pk=mark.pk).exists())
        self.assertTrue(Subject.objects.filter(pk=self.subject.id).exists())

        deleted = self.client.delete(url, {"confirm": True}, format="json")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Subject.objects.filter(pk=self.subject.id).exists())
        self.assertFalse(Performance.objects.filter(pk=mark.pk).exists())

    def test_year_cannot_shrink_past_terms(self):
        r = self.patch(self.admin_a, f"/api/academic-years/{self.year.id}/", {"end_date": "2026-02-01"})
        self.assertEqual(r.status_code, 400)

    def test_term_must_stay_inside_year(self):
        r = self.patch(self.admin_a, f"/api/terms/{self.term.id}/", {"end_date": "2027-02-01"})
        self.assertEqual(r.status_code, 400)

    def test_enrollment_rules(self):
        e1 = Enrollment.objects.create(
            student=self.student, academic_year=self.year, class_level=self.l1, stream=self.stream)
        e2 = Enrollment.objects.create(
            student=self.student, academic_year=self.year, class_level=self.l1, is_active=False)
        r = self.patch(self.admin_a, f"/api/enrollments/{e2.id}/", {"is_active": True})
        self.assertEqual(r.status_code, 400)
        r = self.patch(self.admin_a, f"/api/enrollments/{e1.id}/", {"stream": self.stream_l2.id})
        self.assertEqual(r.status_code, 400)
        r = self.patch(self.admin_a, f"/api/enrollments/{e1.id}/", {"is_active": False})
        self.assertEqual(r.status_code, 200)

    def test_teacher_assignment_delete(self):
        url = f"/api/teacher-assignments/{self.assign.id}/"
        self.client.force_authenticate(self.t_user)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.client.force_authenticate(self.admin_b)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(TeacherAssignment.objects.count(), 0)
