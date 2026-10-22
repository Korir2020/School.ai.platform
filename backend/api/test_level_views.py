from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.level_rules import create_scale
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, School, SchoolAdminProfile, Stream,
    Student, Subject, TeacherAssignment, TeacherProfile, Term,
)


class LevelViewsTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.school = School.objects.create(name="Route School", code="rt-test")
        self.other = School.objects.create(name="Other Route", code="rt-other")
        self.admin = U.objects.create_user("rt_admin", "a@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.teacher = U.objects.create_user("rt_teacher", "t@example.com", "pw12345!")
        tp = TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.outsider = U.objects.create_user("rt_out", "o@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.outsider, school=self.other)
        self.cur = Curriculum.objects.create(name="Route CBC", code="RCBC")
        g3 = ClassLevel.objects.create(curriculum=self.cur, name="Grade 3", level_number=3)
        self.east = Stream.objects.create(school=self.school, class_level=g3, name="East")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1), end_date=date(2026, 4, 30))
        self.math = Subject.objects.create(school=self.school, name="Mathematics")
        TeacherAssignment.objects.create(teacher=tp, school=self.school, subject=self.math, stream=self.east)
        self.kid = Student.objects.create(
            school=self.school, first_name="Amani", last_name="Test", admission_number="A1")
        Enrollment.objects.create(student=self.kid, academic_year=self.year, class_level=g3, stream=self.east)
        create_scale(self.school, self.cur, 1, 6, self.admin)

    def _c(self, user=None):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        return c

    def _body(self, **kw):
        d = {"student_id": self.kid.id, "subject_id": self.math.id, "year_id": self.year.id,
             "term_id": self.term.id, "type": "end", "level": "meets", "comment": "Good"}
        d.update(kw)
        return d

    def test_login_required(self):
        self.assertIn(self._c().get("/api/levels/scales/").status_code, (401, 403))

    def test_teacher_saves_and_roster_shows_it(self):
        r = self._c(self.teacher).post("/api/levels/save/", self._body(), format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "draft")
        q = (f"?subject_id={self.math.id}&stream_id={self.east.id}"
             f"&year_id={self.year.id}&term_id={self.term.id}&type=end")
        d = self._c(self.teacher).get("/api/levels/roster/" + q).json()
        self.assertEqual(d["rows"][0]["level"], "meets")
        self.assertEqual(len(d["levels"]), 4)

    def test_free_text_level_rejected(self):
        r = self._c(self.teacher).post("/api/levels/save/", self._body(level="brilliant"), format="json")
        self.assertEqual(r.status_code, 400)

    def test_other_school_cannot_see_or_save(self):
        r = self._c(self.outsider).post("/api/levels/save/", self._body(), format="json")
        self.assertEqual(r.status_code, 404)

    def test_move_flow_and_permissions(self):
        rid = self._c(self.teacher).post("/api/levels/save/", self._body(), format="json").json()["id"]
        mv = lambda u, a: self._c(u).post("/api/levels/move/", {"result_id": rid, "action": a}, format="json")
        self.assertEqual(mv(self.teacher, "submit").status_code, 200)
        self.assertEqual(mv(self.teacher, "approve").status_code, 400)
        self.assertEqual(mv(self.outsider, "approve").status_code, 404)
        self.assertEqual(mv(self.admin, "approve").json()["status"], "approved")

    def test_scales_admin_only_to_change(self):
        self.assertEqual(self._c(self.teacher).get("/api/levels/scales/").status_code, 200)
        body = {"curriculum_id": self.cur.id, "min_level": 1, "max_level": 6}
        self.assertEqual(self._c(self.teacher).post("/api/levels/scales/", body, format="json").status_code, 400)
        r = self._c(self.admin).post("/api/levels/scales/", body, format="json")
        self.assertEqual((r.status_code, r.json()["version"]), (200, 2))
