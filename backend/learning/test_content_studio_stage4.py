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
