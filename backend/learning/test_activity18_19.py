from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import LearningOfflineOperation, LearningProfile

User = get_user_model()


class Activity18MotivationAndActivity19OfflineTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("activity1819", password="Activity1819!123")
        now = timezone.now()
        self.profile = LearningProfile.objects.create(
            user=self.user,
            account_kind="public_learner",
            age_band="adult",
            age_verified_at=now,
            age_verification_source="provider",
            contact_verified_at=now,
            contact_verification_channel="email",
            consent_state="not_required",
        )
        self.client.force_authenticate(self.user)

    def test_motivation_is_learner_owned_and_disableable(self):
        response = self.client.get("/api/learning/v1/motivation/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["streak_days"], 0)
        response = self.client.patch("/api/learning/v1/motivation/", {"enabled": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["enabled"])

    def test_offline_package_requires_opaque_device_and_returns_expiry(self):
        response = self.client.post(
            "/api/learning/v1/offline/packages/",
            {"device_id": "device-activity1819", "resource_ids": [], "path_ids": [], "lang": "en"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertIn("package_id", data)
        self.assertIn("expires_at", data)
        self.assertEqual(data["encryption"]["algorithm"], "AES-GCM")
        package_id = data["package_id"]
        response = self.client.post(
            "/api/learning/v1/offline/sync/",
            {"package_id": package_id, "device_id": "device-activity1819", "operations": [{"operation_id": "not-a-uuid", "item_type": "resource", "item_id": 1, "event_type": "progress", "details": {}}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["conflicts"], 1)
        self.assertEqual(LearningOfflineOperation.objects.count(), 0)

    def test_offline_package_does_not_cross_learner_boundary(self):
        response = self.client.post(
            "/api/learning/v1/offline/packages/",
            {"device_id": "device-boundary-1819", "resource_ids": [], "path_ids": [], "lang": "en"},
            format="json",
        )
        package_id = response.json()["package_id"]
        other = User.objects.create_user("activity1819_other", password="Activity1819!123")
        now = timezone.now()
        LearningProfile.objects.create(
            user=other, account_kind="public_learner", age_band="adult",
            age_verified_at=now, age_verification_source="provider",
            contact_verified_at=now, contact_verification_channel="email",
            consent_state="not_required",
        )
        self.client.force_authenticate(other)
        response = self.client.post(
            "/api/learning/v1/offline/sync/",
            {"package_id": package_id, "device_id": "device-boundary-1819", "operations": []},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
