"""API tests for the per-school report options."""
import unittest
try:
    import marian_reports  # noqa: F401
except ImportError:
    raise unittest.SkipTest("marian_reports is not installed")

from django.test import TestCase
from rest_framework.test import APIClient
from marian_reports.config import ReportConfig

from api import test_report_views as tv
from api.report_access import build_report_user
from api.report_options import OptionError, apply_options, effective_options, validate_options
from api.report_source import DjangoAuditLog
from schools.models import ReportSettings


class OptionsCase(TestCase):
    def setUp(self):
        tv.ApiCase.setUp(self)
        self.url = tv.B + "options/"

    def call(self, method, user, data=None):
        c = APIClient()
        c.force_authenticate(user)
        if method == "get":
            return c.get(self.url)
        return getattr(c, method)(self.url, data or {}, format="json")

    def put(self, user, options):
        return self.call("put", user, {"options": options})

    def test_defaults_keep_todays_behaviour(self):
        r = self.call("get", self.admin)
        self.assertEqual(r.status_code, 200, r.data)
        o = r.data["options"]
        self.assertEqual((o["previous_exams"], o["rank_by"], o["tie_policy"],
                          o["allow_provisional"], o["weak_pct"]),
                         (3, "best_points", "competition", False, 50))

    def test_save_and_read_back(self):
        want = {"previous_exams": 2, "rank_by": "total_marks", "tie_policy": "dense",
                "allow_provisional": True, "weak_pct": 40, "footer_note": "Pay fees on time."}
        r = self.put(self.admin, want)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.call("get", self.admin).data["options"], want)

    def test_bad_values_are_rejected_and_nothing_saved(self):
        bad = [{"previous_exams": 5}, {"previous_exams": 0}, {"previous_exams": "2"},
               {"previous_exams": True}, {"tie_policy": "x"}, {"rank_by": "x"},
               {"weak_pct": 101}, {"weak_pct": -1}, {"weak_pct": True},
               {"allow_provisional": "yes"}, {"nonsense": 1}, {"footer_note": "x" * 201}]
        for b in bad:
            r = self.put(self.admin, b)
            self.assertEqual((r.status_code, r.data["error"]), (400, "invalid_options"), b)
        self.assertEqual(self.call("put", self.admin, {"options": ["x"]}).status_code, 400)
        self.assertEqual(self.call("put", self.admin, {}).status_code, 400)
        row = ReportSettings.objects.filter(school_id=self.school.id).first()
        self.assertTrue(row is None or not row.options)

    def test_only_admins_and_schools_are_separate(self):
        self.assertEqual(self.call("get", self.t3).status_code, 403)
        self.assertEqual(self.put(self.t3, {"previous_exams": 1}).status_code, 403)
        self.assertEqual(self.call("get", self.gua).status_code, 403)
        self.assertEqual(self.put(self.admin2, {"previous_exams": 1}).status_code, 200)
        self.assertEqual(self.call("get", self.admin).data["options"]["previous_exams"], 3)

    def test_change_is_audited(self):
        self.put(self.admin, {"tie_policy": "ordinal"})
        entries = DjangoAuditLog().entries(build_report_user(self.admin), None, 50)
        self.assertTrue(any("options" in str(e).lower() for e in entries), entries)

    def test_empty_footer_resets_to_default(self):
        default = ReportConfig().footer_note
        self.put(self.admin, {"footer_note": "Custom."})
        self.assertEqual(self.call("get", self.admin).data["options"]["footer_note"], "Custom.")
        self.put(self.admin, {"footer_note": ""})
        self.assertEqual(self.call("get", self.admin).data["options"]["footer_note"], default)

    def test_apply_options_sets_the_report_config(self):
        cfg = ReportConfig()
        apply_options(cfg, {"previous_exams": 2, "rank_by": "total_marks", "tie_policy": "ordinal",
                            "weak_pct": 45, "allow_provisional": True, "footer_note": "Hello."})
        self.assertEqual((cfg.history_limit, cfg.rank_by, cfg.tie_policy, cfg.weak_pct,
                          cfg.allow_provisional, cfg.footer_note),
                         (3, "total_marks", "ordinal", 45.0, True, "Hello."))
        self.assertIn("total marks", cfg.rank_note)
        cfg2 = ReportConfig()
        apply_options(cfg2, {})
        self.assertEqual(effective_options(cfg2)["previous_exams"], 3)

    def test_validate_options_direct(self):
        self.assertEqual(validate_options({"footer_note": "  "}), {"footer_note": None})
        with self.assertRaises(OptionError):
            validate_options(None)
