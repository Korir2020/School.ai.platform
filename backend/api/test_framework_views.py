from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, School, SchoolAdminProfile, TeacherProfile,
)

URL = "/api/frameworks/"


class FrameworkViewsTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.school = School.objects.create(name="Fw School", code="fw-test")
        self.other = School.objects.create(name="Other Fw", code="fw-other")
        self.admin = U.objects.create_user("fw_admin", "a@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school)
        self.second = U.objects.create_user("fw_second", "s@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.second, school=self.school)
        self.teacher = U.objects.create_user("fw_teacher", "t@example.com", "pw12345!")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.outsider = U.objects.create_user("fw_out", "o@example.com", "pw12345!")
        SchoolAdminProfile.objects.create(user=self.outsider, school=self.other)
        self.cur = Curriculum.objects.create(name="Fw CBC", code="FWCBC")
        self.g3 = ClassLevel.objects.create(curriculum=self.cur, name="Grade 3", level_number=3)
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))

    def _c(self, user=None):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        return c

    def _version(self, lo=1, hi=6, key="cbe_junior_levels", user=None):
        return self._c(user or self.admin).post(URL + "version/", {
            "framework_key": key, "curriculum_id": self.cur.id,
            "min_level": lo, "max_level": hi}, format="json")

    def test_teacher_is_forbidden(self):
        self.assertEqual(self._c(self.teacher).get(URL).status_code, 403)

    def test_overview_lists_options(self):
        r = self._c(self.admin).get(URL)
        self.assertEqual(r.status_code, 200)
        keys = [f["key"] for f in r.data["frameworks"]]
        self.assertIn("kcse_844", keys)
        self.assertTrue(any(c["id"] == self.g3.id for c in r.data["class_levels"]))

    def test_create_version_and_assign_default(self):
        r = self._version()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["version"], 1)
        a = self._c(self.admin).post(URL + "assign/", {"version_id": r.data["id"]}, format="json")
        self.assertEqual(a.status_code, 200)
        ov = self._c(self.admin).get(URL)
        row = [e for e in ov.data["effective"] if e["class_level_id"] == self.g3.id][0]
        self.assertEqual(row["framework_key"], "cbe_junior_levels")

    def test_unknown_framework_is_refused(self):
        r = self._version(key="no_such_framework")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"], "framework_error")

    def test_version_must_cover_the_class_level(self):
        r = self._version(lo=1, hi=2)
        a = self._c(self.admin).post(URL + "assign/", {
            "version_id": r.data["id"], "class_level_id": self.g3.id}, format="json")
        self.assertEqual(a.status_code, 400)

    def test_bad_second_approver_is_refused(self):
        r = self._version()
        a = self._c(self.admin).post(URL + "assign/", {
            "version_id": r.data["id"], "approver_username": "fw_second",
            "approver_password": "wrong"}, format="json")
        self.assertEqual(a.status_code, 400)
        self.assertEqual(a.data["error"], "approver_failed")

    def test_other_school_cannot_use_this_version(self):
        r = self._version()
        a = self._c(self.outsider).post(URL + "assign/", {"version_id": r.data["id"]}, format="json")
        self.assertEqual(a.status_code, 404)

    def _freeze(self):
        return self._c(self.admin).post(URL + "version/", {
            "framework_key": "cbe_junior_levels", "curriculum_id": self.cur.id,
            "min_level": 1, "max_level": 6, "freeze_school_scale": True}, format="json")

    def test_freeze_needs_a_school_scale(self):
        r = self._freeze()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["error"], "no_grading_scale")

    def test_freeze_copies_the_current_school_scale(self):
        from api.report_source import DjangoConfigStore, scheme_from_dict
        DjangoConfigStore(str(self.school.id)).save_scheme(scheme_from_dict({
            "bands": [["X", 0, 50, 1], ["Y", 50, 100, 2]], "pass_pct": 50, "decimals": 2,
            "rounding": "half_up", "mean_rule": "total_over_max",
            "absent_policy": "pending", "best_n": None}))
        r = self._freeze()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["frozen_scale"])
        ov = self._c(self.admin).get(URL)
        self.assertTrue(ov.data["versions"][0]["frozen_scale"])

    def test_plain_version_is_not_frozen(self):
        r = self._version()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["frozen_scale"])
