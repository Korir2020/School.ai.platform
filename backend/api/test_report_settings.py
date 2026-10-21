"""API tests for the admin settings views (needs marian_reports)."""
import unittest
try:
    import marian_reports  # noqa: F401
except ImportError:
    raise unittest.SkipTest("marian_reports is not installed")

from django.test import TestCase
from rest_framework.test import APIClient
from marian_reports.section_setup import allowed_keys
from api import test_report_views as tv
from api.report_access import build_report_user
from api.report_source import DjangoAuditLog, DjangoConfigStore
from api.report_views import service

NEW = {"bands": [["E", 0, 50, 1], ["C", 50, 90, 2], ["A", 90, 100, 3]],
       "pass_pct": 50, "decimals": 2, "rounding": "half_up",
       "mean_rule": "total_over_max", "absent_policy": "pending", "best_n": None}


class SettingsCase(TestCase):
    def setUp(self):
        tv.ApiCase.setUp(self)
        self.base = tv.B

    def call(self, method, path, user=None, data=None):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        if method == "get":
            return c.get(self.base + path, data or {})
        return getattr(c, method)(self.base + path, data or {}, format="json")

    def maxes(self, user):
        return [float(b[2]) for b in self.call("get", "grading-config/", user).data["bands"]]

    def maths_grade(self):
        user, svc = build_report_user(self.admin), service(self.school.id)
        snap = svc.snapshot(user, str(self.exam.pk), "Form 3")
        rd = svc.build_report(user, snap, str(self.s1.pk))
        return next(l.grade for l in rd.subjects if l.subject.lower().startswith("math"))

    def test_non_admin_forbidden(self):
        for who in (self.gua, self.t3):
            for m, p, d in (("get", "grading-config/", None), ("put", "grading-config/", NEW),
                            ("get", "section-config/", None), ("put", "section-config/", {"sections": {}}),
                            ("get", "audit/", None)):
                self.assertEqual(self.call(m, p, who, d).status_code, 403, (who.username, m, p))

    def test_each_school_has_own_scale(self):
        self.assertEqual(self.call("put", "grading-config/", self.admin2, NEW).status_code, 200)
        self.assertEqual(self.maxes(self.admin), [50.0, 70.0, 100.0])
        self.assertEqual(self.maxes(self.admin2), [50.0, 90.0, 100.0])

    def test_overlapping_bands_rejected(self):
        bad = {**NEW, "bands": [["E", 0, 60, 1], ["C", 50, 100, 2]]}
        r = self.call("put", "grading-config/", self.admin, bad)
        self.assertEqual((r.status_code, r.data["error"]), (400, "invalid_grading"))
        self.assertEqual(self.maxes(self.admin), [50.0, 70.0, 100.0])

    def test_valid_change_persists_and_is_audited(self):
        self.assertEqual(self.call("put", "grading-config/", self.admin, NEW).status_code, 200)
        self.assertEqual(self.maxes(self.admin), [50.0, 90.0, 100.0])
        top = max(service(self.school.id).scheme.bands, key=lambda b: b.min_pct)
        self.assertEqual(float(top.min_pct), 90.0)
        rows = DjangoAuditLog().entries(build_report_user(self.admin), "grading_scale.changed", 10)
        self.assertEqual(len(rows), 1)

    def test_no_scale_yet_reports_unconfigured(self):
        r = self.call("get", "grading-config/", self.admin3)
        self.assertEqual((r.status_code, r.data["configured"]), (200, False))
        self.assertIn("rounding", r.data["options"])

    def test_section_toggle_persists(self):
        key = sorted(allowed_keys())[0]
        cur = self.call("get", "section-config/", self.admin).data["sections"][key]
        r = self.call("put", "section-config/", self.admin, {"sections": {key: not cur}})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn(key, r.data["changed"])
        self.assertEqual(self.call("get", "section-config/", self.admin).data["sections"][key], not cur)
        self.assertEqual(DjangoConfigStore(str(self.school.id)).saved_sections(), {key: not cur})
        self.assertEqual(self.call("get", "section-config/", self.admin2).data["sections"][key], cur)

    def test_bad_sections_rejected(self):
        key = sorted(allowed_keys())[0]
        for body in ({"sections": {"nope_key": True}}, {"sections": {key: "yes"}}, {}):
            r = self.call("put", "section-config/", self.admin, body)
            self.assertEqual((r.status_code, r.data["error"]), (400, "invalid_sections"), body)

    def test_audit_list_scoped_to_school(self):
        self.call("put", "grading-config/", self.admin, NEW)
        mine = self.call("get", "audit/", self.admin)
        self.assertEqual(mine.status_code, 200)
        self.assertIn("grading_scale.changed", str(mine.data["entries"]))
        self.assertEqual(self.call("get", "audit/", self.admin2).data["entries"], [])

    def test_changing_boundaries_changes_grades(self):
        self.assertEqual(self.maths_grade(), "A")        # 70 marks, A starts at 70
        self.call("put", "grading-config/", self.admin, NEW)
        self.assertEqual(self.maths_grade(), "C")        # A now starts at 90

    def test_malformed_body_is_400(self):
        for body in ({"bands": "abc", "pass_pct": 50}, {}, {**NEW, "decimals": "x"}):
            r = self.call("put", "grading-config/", self.admin, body)
            self.assertEqual((r.status_code, r.data["error"]), (400, "invalid_grading"), body)
