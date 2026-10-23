from django.test import TestCase
from rest_framework.test import APIClient

from api import test_report_views as tv
from api.report_access import build_report_user
from api.report_views import service
from schools.models import FrameworkVersion

ZZ = {"bands": [["ZZ-LOW", 0, 50, 1], ["ZZ-MID", 50, 90, 2], ["ZZ-HIGH", 90, 100, 3]],
      "pass_pct": 50, "decimals": 2, "rounding": "half_up",
      "mean_rule": "total_over_max", "absent_policy": "pending", "best_n": None}
QQ = {"bands": [["QQ-LOW", 0, 50, 1], ["QQ-HIGH", 50, 100, 2]],
      "pass_pct": 50, "decimals": 2, "rounding": "half_up",
      "mean_rule": "total_over_max", "absent_policy": "pending", "best_n": None}


class ExamFrameworkScaleTests(TestCase):
    def setUp(self):
        tv.ApiCase.setUp(self)

    def _stamp(self, rules, version=1, key="cbe_junior_levels"):
        FrameworkVersion.objects.create(
            school=self.school, framework_key=key, version=version,
            curriculum=self.level.curriculum, min_level=3, max_level=4,
            source="school", rules=rules)
        self.exam.framework_key = key
        self.exam.framework_version = version
        self.exam.save()

    def _grade(self):
        user = build_report_user(self.admin)
        svc = service(self.school.id, str(self.exam.pk))
        snap = svc.snapshot(user, str(self.exam.pk), "Form 3")
        rd = svc.build_report(user, snap, str(self.s1.pk))
        return next(l.grade for l in rd.subjects if l.subject.lower().startswith("math"))

    def test_legacy_exam_uses_the_school_scale(self):
        self.assertFalse(self._grade().startswith("ZZ"))

    def test_exam_with_a_frozen_scale_uses_its_bands(self):
        self._stamp({"scheme": ZZ})
        self.assertEqual(self._grade(), "ZZ-MID")

    def test_editing_the_school_scale_does_not_move_a_frozen_exam(self):
        self._stamp({"scheme": ZZ})
        c = APIClient()
        c.force_authenticate(self.admin)
        r = c.put(tv.B + "grading-config/", QQ, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._grade(), "ZZ-MID")
        self.exam.framework_key = None
        self.exam.framework_version = None
        self.exam.save()
        self.assertEqual(self._grade(), "QQ-HIGH")

    def test_version_without_a_frozen_scale_uses_the_school_scale(self):
        self._stamp({})
        self.assertFalse(self._grade().startswith("ZZ"))

    def test_missing_version_row_falls_back_to_the_school_scale(self):
        self.exam.framework_key = "cbe_junior_levels"
        self.exam.framework_version = 99
        self.exam.save()
        self.assertFalse(self._grade().startswith("ZZ"))

    def test_pdf_route_works_for_a_frozen_exam(self):
        self._stamp({"scheme": ZZ})
        c = APIClient()
        c.force_authenticate(self.admin)
        r = c.get(tv.B + "student/%d/pdf/" % self.s1.pk, self.q)
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))
