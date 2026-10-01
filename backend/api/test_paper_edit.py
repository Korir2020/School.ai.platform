from datetime import date

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Exam, Performance, School,
    SchoolAdminProfile, Student, Subject, SubjectPaper, TeacherProfile, Term,
)


class PaperEditTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="A", code="A1")
        other = School.objects.create(name="B", code="B1")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="T1",
            start_date=date(2026, 1, 5), end_date=date(2026, 4, 5))
        cur = Curriculum.objects.create(name="C", code="C1")
        self.level = ClassLevel.objects.create(curriculum=cur, name="L1", level_number=1)
        self.student = Student.objects.create(
            school=self.school, first_name="Ann", last_name="A", admission_number="A-1")
        self.open_subj = Subject.objects.create(school=self.school, name="Math")
        self.used_subj = Subject.objects.create(school=self.school, name="English")
        self.open_p1 = SubjectPaper.objects.create(subject=self.open_subj, paper_number=1, weight=60)
        self.open_p2 = SubjectPaper.objects.create(subject=self.open_subj, paper_number=2, weight=40)
        self.used_p1 = SubjectPaper.objects.create(subject=self.used_subj, paper_number=1, weight=100)
        Performance.objects.create(
            student=self.student, subject=self.used_subj, academic_year=self.year,
            term=self.term, assessment_type="end", marks=50, status="locked")
        Exam.objects.create(
            school=self.school, name="End T1", term=self.term, class_level=self.level,
            assessment_type="end", status="published", published_at=timezone.now())
        self.admin = User.objects.create_user("admin", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher = User.objects.create_user("teacher", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.other_admin = User.objects.create_user("other", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=other)

    def patch(self, user, paper, weight):
        self.client.force_authenticate(user)
        return self.client.patch(f"/api/subject-papers/{paper.id}/", {"weight": weight}, format="json")

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(f"/api/subject-papers/{self.open_p1.id}/").status_code, 401)

    def test_teacher_reads_but_cannot_change(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(f"/api/subject-papers/{self.open_p1.id}/").status_code, 200)
        self.assertEqual(self.patch(self.teacher, self.open_p1, 50).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/subject-papers/{self.open_p1.id}/").status_code, 403)

    def test_other_school_gets_404(self):
        self.assertEqual(self.patch(self.other_admin, self.open_p1, 50).status_code, 404)

    def test_admin_changes_weight_on_open_subject(self):
        self.assertEqual(self.patch(self.admin, self.open_p1, 50).status_code, 200)
        self.open_p1.refresh_from_db()
        self.assertEqual(float(self.open_p1.weight), 50.0)

    def test_total_cannot_exceed_100(self):
        self.assertEqual(self.patch(self.admin, self.open_p1, 70).status_code, 400)

    def test_only_weight_editable(self):
        self.client.force_authenticate(self.admin)
        r = self.client.patch(f"/api/subject-papers/{self.open_p1.id}/", {"paper_number": 9}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_locked_after_publish(self):
        self.assertEqual(self.patch(self.admin, self.used_p1, 90).status_code, 409)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f"/api/subject-papers/{self.used_p1.id}/").status_code, 409)
        r = self.client.post("/api/subject-papers/",
                             {"subject": self.used_subj.id, "paper_number": 2, "weight": 0}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(SubjectPaper.objects.filter(subject=self.used_subj).count(), 1)

    def test_delete_on_open_subject(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(f"/api/subject-papers/{self.open_p2.id}/").status_code, 204)
