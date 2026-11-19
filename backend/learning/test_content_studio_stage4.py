from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from learning.models import LearningContentRole
from learning.test_content_api import BASE

User = get_user_model()
PLATFORM = BASE.replace("studio/", "platform/")
PW = "Content!123456"


class ContentStudioStage4Tests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user("s4_author", password=PW)
        self.curator = User.objects.create_user("s4_curator", password=PW)
        self.superuser = User.objects.create_superuser("s4_super", password=PW)
        self.staff = User.objects.create_user(
            "s4_staff", password=PW, is_staff=True)
        LearningContentRole.objects.create(user=self.author, role="author")
        LearningContentRole.objects.create(user=self.curator, role="curator")

    def submitted(self):
        self.client.force_authenticate(self.author)
        r = self.client.post(PLATFORM + "resources/", {
            "title": "S4 lesson", "summary": "S", "body": "Text",
            "language_code": "en", "practice_quiz": {},
            "age_min": 10, "age_max": 16,
            "source_name": "Marian", "license_name": "Marian-owned",
            "source_type": "marian_original",
            "attribution": "Created by Marian."}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        rid = r.json()["id"]
        s = self.client.post(
            PLATFORM + f"resources/{rid}/submit/", {}, format="json")
        self.assertEqual(s.status_code, 200, s.content)
        return rid

    def review_as(self, user, rid):
        self.client.force_authenticate(user)
        return self.client.post(
            PLATFORM + f"resources/{rid}/review/",
            {"decision": "approve"}, format="json")

    def test_stage4_inactive_curator_refused(self):
        rid = self.submitted()
        LearningContentRole.objects.filter(
            user=self.curator, role="curator").update(is_active=False)
        self.assertEqual(self.review_as(self.curator, rid).status_code, 403)

    def test_stage4_superuser_and_staff_without_role_refused(self):
        rid = self.submitted()
        self.assertEqual(self.review_as(self.superuser, rid).status_code, 403)
        self.assertEqual(self.review_as(self.staff, rid).status_code, 403)

    def test_stage4_active_curator_approves_and_stamps_verifier(self):
        rid = self.submitted()
        r = self.review_as(self.curator, rid)
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["license_verified_by_id"], self.curator.pk)

    def revoke(self, user, **body):
        self.client.force_authenticate(user)
        return self.client.post(PLATFORM + "roles/revoke/", body, format="json")

    def test_stage4_only_superuser_can_revoke(self):
        b = {"user_id": self.curator.pk, "role": "curator"}
        self.assertEqual(self.revoke(self.staff, **b).status_code, 403)
        self.assertEqual(self.revoke(self.author, **b).status_code, 403)
        self.assertTrue(LearningContentRole.objects.get(
            user=self.curator, role="curator").is_active)

    def test_stage4_revoke_deactivates_audits_and_blocks_review(self):
        rid = self.submitted()
        r = self.revoke(self.superuser, user_id=self.curator.pk, role="curator")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(LearningContentRole.objects.get(
            user=self.curator, role="curator").is_active)
        from learning.models import LearningAuditEvent
        self.assertTrue(LearningAuditEvent.objects.filter(
            action="content_role_revoked", actor=self.superuser).exists())
        self.assertEqual(self.review_as(self.curator, rid).status_code, 403)

    def test_stage4_revoke_unknown_role_or_user(self):
        self.assertEqual(self.revoke(
            self.superuser, user_id=self.staff.pk, role="curator").status_code, 404)
        self.assertEqual(self.revoke(
            self.superuser, user_id=self.curator.pk, role="admin").status_code, 400)

    def pt_takedown(self, user, rid, **body):
        self.client.force_authenticate(user)
        return self.client.post(
            PLATFORM + f"resources/{rid}/takedown/", body, format="json")

    def test_stage5_curator_takes_down_platform_content(self):
        rid = self.submitted()
        r = self.pt_takedown(self.curator, rid, reason="Rights holder objected")
        self.assertEqual(r.status_code, 200, r.content)
        from learning.models import LearningAuditEvent, LearningResource
        o = LearningResource.objects.get(pk=rid)
        self.assertEqual(o.status, "archived")
        self.assertEqual(o.takedown_reason, "Rights holder objected")
        self.assertEqual(o.taken_down_by_id, self.curator.pk)
        self.assertIsNotNone(o.taken_down_at)
        self.assertTrue(LearningAuditEvent.objects.filter(
            action="resource_taken_down", actor=self.curator).exists())

    def test_stage5_only_active_curator_may_take_down(self):
        rid = self.submitted()
        for u in (self.superuser, self.staff, self.author):
            self.assertEqual(
                self.pt_takedown(u, rid, reason="r").status_code, 403)
        LearningContentRole.objects.filter(
            user=self.curator, role="curator").update(is_active=False)
        self.assertEqual(
            self.pt_takedown(self.curator, rid, reason="r").status_code, 403)

    def test_stage5_platform_reason_rules_and_repeat(self):
        rid = self.submitted()
        self.assertEqual(self.pt_takedown(self.curator, rid).status_code, 400)
        self.assertEqual(
            self.pt_takedown(self.curator, rid, reason=" ").status_code, 400)
        self.assertEqual(self.pt_takedown(
            self.curator, rid, reason="x" * 501).status_code, 400)
        self.assertEqual(
            self.pt_takedown(self.curator, rid, reason="ok").status_code, 200)
        self.assertEqual(
            self.pt_takedown(self.curator, rid, reason="ok").status_code, 409)

    def test_stage5_school_content_is_not_reachable_here(self):
        from django.contrib.auth import get_user_model
        from learning.models import LearningResource
        from schools.models import School
        sch = School.objects.create(name="S5 School", code="S5X")
        o = LearningResource.objects.create(
            scope="school", school=sch, author=self.author, status="draft",
            version=1, title="T", summary="S", body="B", language_code="en",
            resource_type="lesson")
        self.assertEqual(
            self.pt_takedown(self.curator, o.pk, reason="r").status_code, 404)
