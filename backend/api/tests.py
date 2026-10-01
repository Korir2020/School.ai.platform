from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import School, Student, TeacherProfile, SchoolAdminProfile


class SchoolIsolationTests(APITestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="A", code="A1")
        self.school_b = School.objects.create(name="B", code="B1")
        Student.objects.create(
            school=self.school_a, first_name="Ann", last_name="A", admission_number="A-1"
        )
        Student.objects.create(
            school=self.school_b, first_name="Ben", last_name="B", admission_number="B-1"
        )
        self.teacher_a = User.objects.create_user("teacher_a", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher_a, school=self.school_a)
        self.admin_b = User.objects.create_user("admin_b", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin_b, school=self.school_b)
        self.nobody = User.objects.create_user("nobody", password="pass12345")
        self.super = User.objects.create_superuser("root", "r@x.com", "pass12345")

    def test_anonymous_gets_401(self):
        for url in ["/api/students/", "/api/subjects/", "/api/performance/"]:
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_user_without_profile_gets_403(self):
        self.client.force_authenticate(self.nobody)
        self.assertEqual(self.client.get("/api/students/").status_code, 403)

    def test_teacher_sees_only_own_school(self):
        self.client.force_authenticate(self.teacher_a)
        names = [s["first_name"] for s in self.client.get("/api/students/").json()]
        self.assertEqual(names, ["Ann"])

    def test_school_admin_sees_only_own_school(self):
        self.client.force_authenticate(self.admin_b)
        names = [s["first_name"] for s in self.client.get("/api/students/").json()]
        self.assertEqual(names, ["Ben"])

    def test_superuser_sees_all(self):
        self.client.force_authenticate(self.super)
        self.assertEqual(len(self.client.get("/api/students/").json()), 2)


from datetime import date
from schools.models import (
    AcademicYear, Term, Curriculum, ClassLevel, Stream,
    Enrollment, Subject, TeacherAssignment,
)


class MarksEntryTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="S", code="S1")
        other = School.objects.create(name="O", code="O1")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="T1",
            start_date=date(2026, 1, 1), end_date=date(2026, 4, 1),
        )
        cur = Curriculum.objects.create(name="CBC", code="CBCX")
        level = ClassLevel.objects.create(curriculum=cur, name="G7", level_number=7)
        self.stream = Stream.objects.create(school=self.school, class_level=level, name="E")
        self.student = Student.objects.create(
            school=self.school, first_name="St", last_name="One", admission_number="S-1"
        )
        self.other_student = Student.objects.create(
            school=other, first_name="Ot", last_name="Her", admission_number="O-1"
        )
        Enrollment.objects.create(
            student=self.student, academic_year=self.year,
            class_level=level, stream=self.stream,
        )
        self.subject = Subject.objects.create(school=self.school, name="Maths", code="M")
        self.good = User.objects.create_user("good", password="pass12345")
        good_profile = TeacherProfile.objects.create(user=self.good, school=self.school)
        TeacherAssignment.objects.create(
            teacher=good_profile, school=self.school,
            subject=self.subject, stream=self.stream,
        )
        self.bad = User.objects.create_user("bad", password="pass12345")
        TeacherProfile.objects.create(user=self.bad, school=self.school)

    def payload(self, marks=70, student=None):
        return {
            "student": (student or self.student).id,
            "subject": self.subject.id,
            "academic_year": self.year.id,
            "term": self.term.id,
            "assessment_type": "end",
            "marks": marks,
        }

    def test_assigned_teacher_can_post(self):
        self.client.force_authenticate(self.good)
        r = self.client.post("/api/performance/", self.payload(), format="json")
        self.assertEqual(r.status_code, 201)

    def test_unassigned_teacher_blocked(self):
        self.client.force_authenticate(self.bad)
        r = self.client.post("/api/performance/", self.payload(), format="json")
        self.assertEqual(r.status_code, 403)

    def test_marks_over_100_rejected(self):
        self.client.force_authenticate(self.good)
        r = self.client.post("/api/performance/", self.payload(marks=101), format="json")
        self.assertEqual(r.status_code, 400)

    def test_cross_school_student_blocked(self):
        self.client.force_authenticate(self.good)
        r = self.client.post(
            "/api/performance/", self.payload(student=self.other_student), format="json"
        )
        self.assertEqual(r.status_code, 403)


class JWTLoginTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="J", code="J1")
        self.user = User.objects.create_user("jt", password="pass12345")
        TeacherProfile.objects.create(user=self.user, school=self.school)

    def test_login_and_me(self):
        r = self.client.post(
            "/api/auth/login/", {"username": "jt", "password": "pass12345"}, format="json"
        )
        self.assertEqual(r.status_code, 200)
        token = r.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        me = self.client.get("/api/auth/me/").json()
        self.assertEqual(me["role"], "teacher")
        self.assertEqual(me["school"]["name"], "J")

    def test_wrong_password_rejected(self):
        r = self.client.post(
            "/api/auth/login/", {"username": "jt", "password": "wrong"}, format="json"
        )
        self.assertEqual(r.status_code, 401)


from schools.models import MarkAuditLog, Performance


class WorkflowTests(APITestCase):
    payload = MarksEntryTests.payload

    def setUp(self):
        MarksEntryTests.setUp(self)
        self.admin = User.objects.create_user("adm", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        other = School.objects.create(name="Other2", code="O2")
        self.other_admin = User.objects.create_user("oadm", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=other)

    def make_mark(self):
        self.client.force_authenticate(self.good)
        r = self.client.post("/api/performance/", self.payload(), format="json")
        return r.json()["id"]

    def act(self, user, pk, action):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/performance/{pk}/{action}/")

    def test_new_mark_is_draft_and_cannot_force_status(self):
        self.client.force_authenticate(self.good)
        data = self.payload()
        data["status"] = "locked"
        r = self.client.post("/api/performance/", data, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Performance.objects.get(pk=r.json()["id"]).status, "draft")
        self.assertTrue(MarkAuditLog.objects.filter(action="created").exists())

    def test_assigned_teacher_can_submit(self):
        pk = self.make_mark()
        self.assertEqual(self.act(self.good, pk, "submit").status_code, 200)
        self.assertEqual(Performance.objects.get(pk=pk).status, "submitted")

    def test_teacher_cannot_approve(self):
        pk = self.make_mark()
        self.act(self.good, pk, "submit")
        self.assertEqual(self.act(self.good, pk, "approve").status_code, 403)

    def test_unassigned_teacher_cannot_submit(self):
        pk = self.make_mark()
        self.assertEqual(self.act(self.bad, pk, "submit").status_code, 403)

    def test_full_flow_then_locked_is_final(self):
        pk = self.make_mark()
        self.assertEqual(self.act(self.good, pk, "submit").status_code, 200)
        self.assertEqual(self.act(self.admin, pk, "approve").status_code, 200)
        self.assertEqual(self.act(self.admin, pk, "lock").status_code, 200)
        self.assertEqual(self.act(self.good, pk, "submit").status_code, 409)
        self.assertEqual(self.act(self.admin, pk, "reject").status_code, 409)
        actions = set(MarkAuditLog.objects.values_list("action", flat=True))
        self.assertTrue({"created", "submit", "approve", "lock"} <= actions)

    def test_other_school_admin_gets_404(self):
        pk = self.make_mark()
        self.assertEqual(self.act(self.other_admin, pk, "approve").status_code, 404)

    def test_cannot_skip_steps(self):
        pk = self.make_mark()
        self.assertEqual(self.act(self.admin, pk, "approve").status_code, 409)
