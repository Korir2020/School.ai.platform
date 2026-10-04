from django.contrib.admin import site
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse
from rest_framework.test import APITestCase

from schools.models import ExamResult, MarkAuditLog, Performance
from . import tests as base


class AdminAuditTests(APITestCase):
    def setUp(self):
        base.ExamPublishTests.setUp(self)
        self.root = User.objects.create_superuser("root9", "r@x.com", "pass12345")
        self.client.force_login(self.root)
        self.req = RequestFactory().post("/")
        self.req.user = self.root

    def perf(self, status):
        return base.ExamPublishTests.mark(self, self.student, 1, 70, status=status)

    def test_locked_mark_cannot_be_changed_or_deleted(self):
        p = self.perf("locked")
        url = reverse("admin:schools_performance_change", args=[p.pk])
        self.assertEqual(self.client.post(url, {"marks": "5"}).status_code, 403)
        self.assertNotIn(b'name="marks"', self.client.get(url).content)
        gone = reverse("admin:schools_performance_delete", args=[p.pk])
        self.assertEqual(self.client.post(gone, {"post": "yes"}).status_code, 403)
        p.refresh_from_db()
        self.assertEqual((str(p.marks), p.status), ("70.00", "locked"))

    def test_admin_edit_and_delete_of_draft_are_logged(self):
        p = self.perf("draft")
        model_admin = site._registry[Performance]
        form = type("F", (), {"changed_data": ["marks"]})()
        p.marks = 55
        model_admin.save_model(self.req, p, form, True)
        log = MarkAuditLog.objects.get(action="admin_edit")
        self.assertEqual(log.details["entity"], "performance")
        self.assertEqual(log.performance_id, p.pk)
        self.assertEqual(log.school_id, self.school.id)
        pk = p.pk
        model_admin.delete_model(self.req, p)
        gone = MarkAuditLog.objects.get(action="admin_delete")
        self.assertEqual(gone.details["id"], pk)
        self.assertFalse(Performance.objects.filter(pk=pk).exists())

    def test_published_exam_and_results_are_protected(self):
        self.perf("approved")
        r = base.ExamPublishTests.publish(self, self.admin)
        self.assertEqual(r.status_code, 200)
        res = ExamResult.objects.get()
        change = reverse("admin:schools_examresult_change", args=[res.pk])
        self.assertEqual(self.client.post(change, {"class_rank": "9"}).status_code, 403)
        add = reverse("admin:schools_examresult_add")
        self.assertEqual(self.client.get(add).status_code, 403)
        exam_url = reverse("admin:schools_exam_change", args=[self.exam.pk])
        self.assertEqual(self.client.post(exam_url, {"name": "X"}).status_code, 403)
        res.refresh_from_db()
        self.assertEqual(res.class_rank, 1)
