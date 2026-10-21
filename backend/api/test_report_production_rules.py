"""Start-up rules in api/report_urls.py, with the environment faked."""
import importlib
import os
import sys
import unittest
from unittest import mock
try:
    import marian_reports  # noqa: F401
except ImportError:
    raise unittest.SkipTest("marian_reports is not installed")

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
import api.report_urls as ru

GOOD = {"MARIAN_REPORT_SECRET": "s" * 40, "MARIAN_VERIFY_BASE": "https://example.test"}


class ProductionRules(SimpleTestCase):
    def tearDown(self):
        importlib.reload(ru)        # restore the real routes for later tests

    def load(self, env, argv=("manage.py", "runserver"), debug=None):
        with mock.patch.dict(os.environ, {}):
            for k in ("DJANGO_DEBUG", "MARIAN_REPORT_SECRET", "MARIAN_VERIFY_BASE"):
                os.environ.pop(k, None)
            os.environ.update(env)
            if debug:
                os.environ["DJANGO_DEBUG"] = debug
            with mock.patch.object(sys, "argv", list(argv)):
                return importlib.reload(ru)

    def test_refuses_without_secret(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "MARIAN_REPORT_SECRET"):
            self.load({"MARIAN_VERIFY_BASE": GOOD["MARIAN_VERIFY_BASE"]})

    def test_refuses_short_secret(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "MARIAN_REPORT_SECRET"):
            self.load({**GOOD, "MARIAN_REPORT_SECRET": "s" * 31})

    def test_refuses_without_verify_base(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "MARIAN_VERIFY_BASE"):
            self.load({"MARIAN_REPORT_SECRET": GOOD["MARIAN_REPORT_SECRET"]})

    def test_starts_with_both_set(self):
        m = self.load(GOOD)
        self.assertGreaterEqual(len(m.report_urlpatterns), 16)

    def test_debug_mode_needs_neither(self):
        m = self.load({}, debug="True")
        self.assertGreaterEqual(len(m.report_urlpatterns), 16)

    def test_test_command_needs_neither(self):
        m = self.load({}, argv=("manage.py", "test"))
        self.assertGreaterEqual(len(m.report_urlpatterns), 16)
