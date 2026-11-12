"""API tests for the comment views (needs marian_reports)."""
import unittest
try:
    import marian_reports  # noqa: F401
except ImportError:
    raise unittest.SkipTest("marian_reports is not installed")

from django.test import TestCase
from rest_framework.test import APIClient
from api import test_report_views as tv
from api.report_access import build_report_user
from api.report_source import DjangoAuditLog, DjangoDataSource
from api.report_views import service


class CommentCase(TestCase):
    def setUp(self):
        tv.ApiCase.setUp(self)          # same school/exam/users as the view tests
        self.base = tv.B + "comments/"

    def call(self, method, path, user=None, data=None):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        if method == "get":
            return c.get(self.base + path, data or {})
        return getattr(c, method)(self.base + path, data or {}, format="json")

    def draft(self, user, field="class_teacher", text="Good steady progress.", student=None):
        return self.call("post", "draft/", user, {
            "exam_id": str(self.exam.pk), "student_id": str((student or self.s1).pk),
            "field": field, "text": text})

    def remarks(self):
        return DjangoDataSource().get_remarks(str(self.school.id), str(self.exam.pk), str(self.s1.pk))

    def test_guardian_blocked(self):
        self.assertEqual(self.call("get", "", self.gua, self.q).status_code, 403)
        self.assertEqual(self.draft(self.gua).status_code, 403)

    def test_teacher_of_other_class_blocked(self):
        self.assertEqual(self.call("get", "", self.t4, self.q).status_code, 403)

    def test_teachers_denied_all_comment_routes(self):
        self.assertEqual(self.draft(self.t3).status_code, 403)
        self.assertEqual(self.call("get", "", self.t3, self.q).status_code, 403)

    def test_teacher_cannot_draft_principal_comment(self):
        self.assertEqual(self.draft(self.t3, field="principal").status_code, 403)

    def test_draft_edit_approve_flow(self):
        r = self.draft(self.admin)
        self.assertEqual(r.status_code, 200, r.data)
        cid = r.data["comment"].get("id")
        self.assertIsNotNone(cid, r.data)
        self.assertIsNone(self.remarks().get("class_teacher"))      # a draft is never on the report
        e = self.call("put", f"{cid}/", self.admin, {"text": "Edited comment text."})
        self.assertEqual(e.status_code, 200, e.data)
        a = self.call("post", f"{cid}/approve/", self.admin)
        self.assertEqual(a.status_code, 200, a.data)
        self.assertEqual(self.remarks().get("class_teacher"), "Edited comment text.")
        lst = self.call("get", "", self.admin, self.q)
        self.assertEqual(lst.status_code, 200)
        self.assertTrue(lst.data["comments"])

    def test_reject_flow(self):
        cid = self.draft(self.admin).data["comment"].get("id")
        r = self.call("post", f"{cid}/reject/", self.admin)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNone(self.remarks().get("class_teacher"))

    def test_invalid_field_is_400(self):
        r = self.draft(self.admin, field="nonsense")
        self.assertEqual((r.status_code, r.data["error"]), (400, "invalid_comment"))

    def test_other_school_gets_404(self):
        self.assertEqual(self.draft(self.admin2).status_code, 404)

    def test_audit_entry_written(self):
        cid = self.draft(self.admin).data["comment"].get("id")
        self.call("post", f"{cid}/approve/", self.admin)
        entries = DjangoAuditLog().entries(build_report_user(self.admin), None, 50)
        self.assertTrue(any("comment" in str(e).lower() for e in entries), entries)

    def test_editable_scale_templates_feed_subject_and_class_comment_suggestions(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        base = "/api/report-module/"
        available = client.get(base + "comment-templates/")
        self.assertEqual(available.status_code, 200, available.data)
        grading = next(row for row in available.data["templates"] if row["key"] == "grading")
        self.assertIn("subject", next(row for row in grading["entries"] if row["key"] == "A")["fields"])

        saved = client.put(base + "comment-templates/", {
            "scale_key": "grading",
            "templates": {
                "A": {
                    "subject": "For {subject}, the recorded {level} result is on the school scale.",
                    "class_teacher": "The current overall result is {level}; review the recorded work.",
                },
            },
        }, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(
            saved.data["template"]["templates"]["A"]["subject"],
            "For {subject}, the recorded {level} result is on the school scale.",
        )

        defaults = client.get(base + "comments/defaults/", {
            "exam_id": str(self.exam.pk), "student_id": str(self.s1.pk),
        })
        self.assertEqual(defaults.status_code, 200, defaults.data)
        self.assertIn("review the recorded work", defaults.data["comments"]["class_teacher"])
        math = next(row for row in defaults.data["subject_comments"] if row["subject"] == "Mathematics")
        self.assertEqual(math["text"], "For Mathematics, the recorded A result is on the school scale.")
        self.assertEqual(self.remarks(), {})  # suggestions never become printable remarks by themselves

        user = build_report_user(self.admin)
        svc = service(self.school.id, str(self.exam.pk))
        snapshot = svc.snapshot(user, str(self.exam.pk), "Form 3")
        report = svc.build_report(user, snapshot, str(self.s1.pk))
        row = next(item for item in report.subjects if item.subject == "Mathematics")
        self.assertEqual(row.remark, math["text"])
