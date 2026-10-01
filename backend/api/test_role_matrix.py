from datetime import date

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, ExamResult,
    MarkAuditLog, Performance, School, SchoolAdminProfile, Stream, Student,
    Subject, SubjectPaper, TeacherAssignment, TeacherProfile, Term,
)


class RoleMatrixTests(APITestCase):
    def setUp(self):
        a = self.a = School.objects.create(name="A", code="A1")
        b = self.b = School.objects.create(name="B", code="B1")
        year = AcademicYear.objects.create(
            school=a, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        term = Term.objects.create(
            academic_year=year, name="T1", start_date=date(2026, 1, 5), end_date=date(2026, 4, 5))
        cur = Curriculum.objects.create(name="C", code="C1")
        level = ClassLevel.objects.create(curriculum=cur, name="L1", level_number=1)
        stream = Stream.objects.create(school=a, class_level=level, name="East")
        student = Student.objects.create(
            school=a, first_name="Ann", last_name="A", admission_number="A-1")
        enrol = Enrollment.objects.create(
            student=student, academic_year=year, class_level=level, stream=stream)
        subject = Subject.objects.create(school=a, name="Math")
        paper = SubjectPaper.objects.create(subject=subject, paper_number=1, weight=100)

        self.teacher = User.objects.create_user("teacher", password="pass12345")
        tp = TeacherProfile.objects.create(user=self.teacher, school=a)
        assign = TeacherAssignment.objects.create(
            teacher=tp, school=a, subject=subject, stream=stream)
        self.admin_a = User.objects.create_user("admin_a", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_a, school=a)
        self.admin_b = User.objects.create_user("admin_b", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_b, school=b)
        self.nobody = User.objects.create_user("nobody", password="pass12345")
        self.root = User.objects.create_superuser("root", "r@x.com", "pass12345")

        perf = Performance.objects.create(
            student=student, subject=subject, academic_year=year, term=term, marks=60)
        exam = Exam.objects.create(
            school=a, name="End", term=term, class_level=level, assessment_type="end",
            status="published", published_at=timezone.now())
        ExamResult.objects.create(exam=exam, student=student, overall_average="60.00",
                                  stream_rank=1, class_rank=1)
        MarkAuditLog.objects.create(performance=perf, school=a, user=self.admin_a, action="created")

        self.shared = ["/api/curriculums/", "/api/class-levels/", "/api/schools/"]
        self.school_lists = [
            "/api/students/", "/api/academic-years/", "/api/terms/", "/api/streams/",
            "/api/enrollments/", "/api/subjects/", "/api/performance/",
            "/api/subject-papers/", "/api/exams/", "/api/teacher-assignments/",
        ]
        self.details = [
            f"/api/students/{student.id}/", f"/api/academic-years/{year.id}/",
            f"/api/terms/{term.id}/", f"/api/streams/{stream.id}/",
            f"/api/subjects/{subject.id}/", f"/api/enrollments/{enrol.id}/",
            f"/api/teacher-assignments/{assign.id}/", f"/api/subject-papers/{paper.id}/",
            f"/api/report-card/{student.id}/{term.id}/",
        ]
        self.admin_only_details = [
            f"/api/analytics/term-summary/{term.id}/",
            f"/api/exams/{exam.id}/results/",
            f"/api/students/{student.id}/exam-history/",
        ]
        self.audit = "/api/audit-logs/"
        self.student_id = student.id
        self.year_id, self.subject_id = year.id, subject.id

    def get(self, user, url):
        self.client.force_authenticate(user)
        return self.client.get(url)

    def every_url(self):
        return (self.shared + self.school_lists + self.details
                + self.admin_only_details + [self.audit])

    def test_anonymous_gets_401_everywhere(self):
        for url in self.every_url():
            self.assertEqual(self.get(None, url).status_code, 401, url)

    def test_no_profile_user_gets_403_everywhere(self):
        for url in self.every_url():
            self.assertEqual(self.get(self.nobody, url).status_code, 403, url)

    def test_no_profile_user_me_role_none(self):
        self.assertEqual(self.get(self.nobody, "/api/auth/me/").json()["role"], "none")

    def test_teacher_access(self):
        for url in self.shared + self.school_lists + self.details:
            self.assertEqual(self.get(self.teacher, url).status_code, 200, url)
        for url in self.admin_only_details + [self.audit]:
            self.assertEqual(self.get(self.teacher, url).status_code, 403, url)

    def test_admin_own_school_access(self):
        for url in self.every_url():
            self.assertEqual(self.get(self.admin_a, url).status_code, 200, url)

    def test_superuser_access(self):
        for url in self.every_url():
            self.assertEqual(self.get(self.root, url).status_code, 200, url)

    def test_other_school_admin_sees_nothing(self):
        for url in self.school_lists:
            r = self.get(self.admin_b, url)
            self.assertEqual((r.status_code, r.json()["results"]), (200, []), url)
        schools = self.get(self.admin_b, "/api/schools/").json()
        self.assertEqual([s["id"] for s in schools["results"]], [self.b.id])
        self.assertEqual(self.get(self.admin_b, self.audit).json(), [])
        for url in self.details + self.admin_only_details:
            self.assertEqual(self.get(self.admin_b, url).status_code, 404, url)

    def test_no_hard_delete_through_api(self):
        self.client.force_authenticate(self.admin_a)
        for url in [f"/api/students/{self.student_id}/",
                    f"/api/academic-years/{self.year_id}/",
                    f"/api/subjects/{self.subject_id}/"]:
            self.assertEqual(self.client.delete(url).status_code, 405, url)
        self.assertTrue(Student.objects.filter(pk=self.student_id).exists())

    def test_login_rules(self):
        self.client.force_authenticate(None)
        ok = self.client.post("/api/auth/login/", {"username": "teacher", "password": "pass12345"})
        self.assertEqual(ok.status_code, 200)
        bad = self.client.post("/api/auth/login/", {"username": "teacher", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        self.teacher.is_active = False
        self.teacher.save()
        gone = self.client.post("/api/auth/login/", {"username": "teacher", "password": "pass12345"})
        self.assertEqual(gone.status_code, 401)
