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


class ReportCardTests(APITestCase):
    def setUp(self):
        MarksEntryTests.setUp(self)
        self.admin = User.objects.create_user("radm", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        other = School.objects.get(code="O1")
        self.other_admin = User.objects.create_user("roadm", password="pass12345")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=other)
        common = dict(student=self.student, subject=self.subject,
                      academic_year=self.year, term=self.term)
        Performance.objects.create(assessment_type="end", marks=80, status="approved", **common)
        Performance.objects.create(assessment_type="mid", marks=50, status="draft", **common)

    def url(self):
        return f"/api/report-card/{self.student.id}/{self.term.id}/"

    def test_only_approved_marks_counted(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["subjects"]), 1)
        self.assertEqual(data["overall_average"], "80.00")
        self.assertEqual(data["pending_marks"], 1)

    def test_other_school_gets_404(self):
        self.client.force_authenticate(self.other_admin)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)


class MarkEditTests(APITestCase):
    payload = MarksEntryTests.payload
    def setUp(self):
        WorkflowTests.setUp(self)
        self.pk = WorkflowTests.make_mark(self)

    def edit(self, user, marks):
        self.client.force_authenticate(user)
        return self.client.patch(
            f"/api/performance/{self.pk}/", {"marks": marks}, format="json"
        )

    def test_assigned_teacher_can_edit_draft_and_it_is_audited(self):
        self.assertEqual(self.edit(self.good, "55").status_code, 200)
        self.assertEqual(str(Performance.objects.get(pk=self.pk).marks), "55.00")
        self.assertTrue(MarkAuditLog.objects.filter(action="edited").exists())

    def test_marks_over_100_rejected(self):
        self.assertEqual(self.edit(self.good, "101").status_code, 400)

    def test_submitted_mark_cannot_be_edited(self):
        WorkflowTests.act(self, self.good, self.pk, "submit")
        self.assertEqual(self.edit(self.good, "55").status_code, 409)

    def test_unassigned_teacher_blocked(self):
        self.assertEqual(self.edit(self.bad, "55").status_code, 403)

    def test_other_school_admin_gets_404(self):
        self.assertEqual(self.edit(self.other_admin, "55").status_code, 404)


class AuditLogTests(APITestCase):
    payload = MarksEntryTests.payload

    def setUp(self):
        WorkflowTests.setUp(self)
        self.pk = WorkflowTests.make_mark(self)

    def get(self, user):
        self.client.force_authenticate(user)
        return self.client.get("/api/audit-logs/")

    def test_admin_sees_own_school_logs(self):
        r = self.get(self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(x["action"] == "created" for x in r.json()))

    def test_teacher_blocked(self):
        self.assertEqual(self.get(self.good).status_code, 403)

    def test_other_school_admin_sees_nothing(self):
        self.assertEqual(self.get(self.other_admin).json(), [])

    def test_anonymous_gets_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/audit-logs/").status_code, 401)


class TermYearMismatchTests(APITestCase):
    payload = MarksEntryTests.payload

    def setUp(self):
        MarksEntryTests.setUp(self)
        self.year2 = AcademicYear.objects.create(
            school=self.school, name="2027",
            start_date=date(2027, 1, 1), end_date=date(2027, 12, 31),
        )

    def test_term_from_other_year_rejected(self):
        self.client.force_authenticate(self.good)
        data = self.payload()
        data["academic_year"] = self.year2.id
        r = self.client.post("/api/performance/", data, format="json")
        self.assertEqual(r.status_code, 400)


class AllEndpointIsolationTests(APITestCase):
    URLS = [
        "/api/schools/", "/api/students/", "/api/academic-years/",
        "/api/terms/", "/api/streams/", "/api/enrollments/",
        "/api/subjects/", "/api/performance/",
    ]

    def setUp(self):
        from schools.models import Performance
        cur = Curriculum.objects.create(name="C", code="CX")
        level = ClassLevel.objects.create(curriculum=cur, name="G7", level_number=7)
        self.schools = {}
        for tag in ("A", "B"):
            school = School.objects.create(name=tag, code=tag + "9")
            year = AcademicYear.objects.create(
                school=school, name="2026",
                start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            )
            term = Term.objects.create(
                academic_year=year, name="T1",
                start_date=date(2026, 1, 1), end_date=date(2026, 4, 1),
            )
            stream = Stream.objects.create(school=school, class_level=level, name="E")
            student = Student.objects.create(
                school=school, first_name=tag, last_name="S", admission_number=tag + "-1"
            )
            Enrollment.objects.create(
                student=student, academic_year=year, class_level=level, stream=stream
            )
            subject = Subject.objects.create(school=school, name="M", code="M" + tag)
            Performance.objects.create(
                student=student, subject=subject, academic_year=year,
                term=term, assessment_type="end", marks=50,
            )
            self.schools[tag] = school
        self.teacher = User.objects.create_user("iso_t", password="pass12345")
        TeacherProfile.objects.create(user=self.teacher, school=self.schools["A"])
        self.root = User.objects.create_superuser("iso_root", "r@x.com", "pass12345")

    def test_teacher_sees_exactly_one_row_per_endpoint(self):
        self.client.force_authenticate(self.teacher)
        for url in self.URLS:
            self.assertEqual(len(self.client.get(url).json()), 1, url)

    def test_superuser_sees_both_schools_per_endpoint(self):
        self.client.force_authenticate(self.root)
        for url in self.URLS:
            self.assertEqual(len(self.client.get(url).json()), 2, url)


class AnalyticsTests(APITestCase):
    payload = MarksEntryTests.payload

    def setUp(self):
        WorkflowTests.setUp(self)
        self.pk = WorkflowTests.make_mark(self)

    def summary(self, user):
        self.client.force_authenticate(user)
        return self.client.get(f"/api/analytics/term-summary/{self.term.id}/")

    def test_draft_marks_not_counted_but_shown_as_pending(self):
        data = self.summary(self.admin).json()
        self.assertEqual(data["subjects"], [])
        self.assertEqual(data["pending_marks"], 1)

    def test_approved_marks_are_averaged(self):
        WorkflowTests.act(self, self.good, self.pk, "submit")
        WorkflowTests.act(self, self.admin, self.pk, "approve")
        data = self.summary(self.admin).json()
        self.assertEqual(data["subjects"][0]["average"], 70.0)
        self.assertEqual(data["pending_marks"], 0)

    def test_teacher_blocked(self):
        self.assertEqual(self.summary(self.good).status_code, 403)

    def test_other_school_admin_gets_404(self):
        self.assertEqual(self.summary(self.other_admin).status_code, 404)

    def test_anonymous_gets_401(self):
        self.client.force_authenticate(None)
        r = self.client.get(f"/api/analytics/term-summary/{self.term.id}/")
        self.assertEqual(r.status_code, 401)
