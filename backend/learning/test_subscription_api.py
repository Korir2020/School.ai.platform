from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningActivityEvent,
    LearningGoal,
    LearningPath,
    LearningPathItem,
    LearningPathParticipation,
    LearningPrivateAsset,
    LearningProfile,
    LearningResource,
    LearningSubscription,
    LearningSubscriptionPlan,
    SavedLearningItem,
)
from schools.models import (
    FeePayment,
    GuardianProfile,
    School,
    Student,
    StudentFee,
    StudentGuardian,
)

User = get_user_model()
BASE = "/api/learning/v1/"


class IndividualSubscriptionApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Subscription Test School", code="SUBTEST")
        self.user = User.objects.create_user("subscription_adult", password="TestPassword!123")
        self.student = Student.objects.create(
            school=self.school,
            first_name="Alex",
            last_name="Learner",
            admission_number="SUB-001",
            date_of_birth=date(1998, 4, 12),
        )
        self.profile = LearningProfile.objects.create(
            user=self.user,
            account_kind="school_student",
            school=self.school,
            student=self.student,
            age_band="adult",
            consent_state="not_required",
        )
        self.reviewer = User.objects.create_user("subscription_reviewer")
        self.free_plan = LearningSubscriptionPlan.objects.get(code="free")
        self.premium_plan = LearningSubscriptionPlan.objects.get(code="premium")

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)

    def make_resource(self, title, *, access_tier="free", storage_key=""):
        now = timezone.now()
        return LearningResource.objects.create(
            scope="public",
            title=title,
            summary="Summary",
            body="A safe lesson body.",
            language_code="en",
            access_tier=access_tier,
            status="published",
            reviewed_by=self.reviewer,
            reviewed_at=now,
            published_at=now,
            storage_key=storage_key,
        )

    def make_path(self, title, *, access_tier="free"):
        now = timezone.now()
        return LearningPath.objects.create(
            scope="public",
            title=title,
            description="A learning journey.",
            objectives=["Learn"],
            language_code="en",
            access_tier=access_tier,
            status="published",
            reviewed_by=self.reviewer,
            reviewed_at=now,
            published_at=now,
        )

    def test_seeded_plans_and_learner_status_are_free_by_default(self):
        plans = self.client.get(f"{BASE}subscriptions/plans/")
        self.assertEqual(plans.status_code, 200, plans.content)
        plan_rows = {row["code"]: row for row in plans.json()["results"]}
        self.assertTrue(plan_rows["free"]["is_active"])
        self.assertTrue(plan_rows["free"]["price_configured"])
        self.assertFalse(plan_rows["premium"]["is_active"])
        self.assertIsNone(plan_rows["premium"]["amount"])
        self.assertFalse(plan_rows["premium"]["price_configured"])

        capabilities = self.client.get(f"{BASE}subscriptions/capabilities/")
        self.assertEqual(capabilities.status_code, 200)
        self.assertFalse(capabilities.json()["checkout_available"])
        self.assertFalse(capabilities.json()["registration_available"])
        self.assertTrue(capabilities.json()["individual_billing_separate"])
        self.assertFalse(capabilities.json()["school_subscription_covers_learning"])

        self.auth()
        status = self.client.get(f"{BASE}subscriptions/me/")
        self.assertEqual(status.status_code, 200, status.content)
        self.assertEqual(status.json()["tier"], "free")
        self.assertEqual(status.json()["subscription_status"], "free")
        self.assertEqual(status.json()["entitlements"]["ai_tutor_requests_per_day"], 0)
        self.assertFalse(status.json()["checkout_available"])

    def test_free_account_cannot_access_premium_catalog_assets_paths_activity_saves_or_goals_without_verified_payment(self):
        free_resource = self.make_resource("Open lesson")
        premium_resource = self.make_resource("Premium lesson", access_tier="premium", storage_key="private/key")
        free_path = self.make_path("Free path")
        premium_path = self.make_path("Premium path", access_tier="premium")
        mixed_path = self.make_path("Free path with premium item")
        LearningPathItem.objects.create(
            path=mixed_path, position=1, item_type="resource", resource=premium_resource,
            completion_rule="view",
        )
        clean_asset = LearningPrivateAsset.objects.create(
            resource=premium_resource,
            storage_name="test-private/subscription-asset.pdf",
            content_type="application/pdf",
            size_bytes=1,
            sha256="a" * 64,
            scan_state="clean",
            scanned_at=timezone.now(),
        )
        # A currently dated active row by itself must not grant premium access.
        LearningSubscription.objects.create(
            profile=self.profile,
            plan=self.premium_plan,
            payer=self.user,
            status="active",
            current_period_start=timezone.now() - timedelta(minutes=1),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        SavedLearningItem.objects.create(profile=self.profile, resource=premium_resource)

        self.auth()
        resources = self.client.get(f"{BASE}catalog/resources/?lang=en")
        self.assertEqual(resources.status_code, 200, resources.content)
        resource_ids = {row["id"] for row in resources.json()["results"]}
        self.assertIn(free_resource.pk, resource_ids)
        self.assertNotIn(premium_resource.pk, resource_ids)
        self.assertEqual(self.client.get(f"{BASE}catalog/resources/{premium_resource.pk}/?lang=en").status_code, 404)

        paths = self.client.get(f"{BASE}catalog/paths/?lang=en")
        self.assertEqual(paths.status_code, 200, paths.content)
        path_ids = {row["id"] for row in paths.json()["results"]}
        self.assertIn(free_path.pk, path_ids)
        self.assertNotIn(premium_path.pk, path_ids)
        self.assertNotIn(mixed_path.pk, path_ids)
        self.assertEqual(self.client.get(f"{BASE}catalog/paths/{premium_path.pk}/?lang=en").status_code, 404)

        download = self.client.get(
            f"{BASE}catalog/resources/{premium_resource.pk}/assets/{clean_asset.pk}/download/?lang=en",
        )
        self.assertEqual(download.status_code, 404)
        self.assertEqual(self.client.post(f"{BASE}paths/{premium_path.pk}/start/", {}, format="json").status_code, 404)

        saved_list = self.client.get(f"{BASE}saved/?lang=en")
        self.assertEqual(saved_list.status_code, 200, saved_list.content)
        self.assertEqual(saved_list.json()["results"], [])
        save_attempt = self.client.post(f"{BASE}saved/?lang=en", {"resource_id": premium_resource.pk}, format="json")
        self.assertEqual(save_attempt.status_code, 404)

        goal_attempt = self.client.post(f"{BASE}goals/", {"title": "Premium goal", "path_id": premium_path.pk}, format="json")
        self.assertEqual(goal_attempt.status_code, 400)
        self.assertEqual(LearningGoal.objects.count(), 0)
        self.assertEqual(LearningPathParticipation.objects.count(), 0)
        self.assertEqual(LearningActivityEvent.objects.count(), 0)

    def test_expired_subscription_falls_back_to_free_and_preserves_learning_history(self):
        old_path = self.make_path("History remains")
        participation = LearningPathParticipation.objects.create(
            profile=self.profile,
            path=old_path,
            path_version=1,
            state="in_progress",
        )
        expired = LearningSubscription.objects.create(
            profile=self.profile,
            plan=self.premium_plan,
            payer=self.user,
            status="expired",
            current_period_start=timezone.now() - timedelta(days=45),
            current_period_end=timezone.now() - timedelta(days=15),
        )
        self.auth()
        status = self.client.get(f"{BASE}subscriptions/me/")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["tier"], "free")
        history = self.client.get(f"{BASE}subscriptions/history/")
        self.assertEqual(history.status_code, 200, history.content)
        self.assertEqual(history.json()["results"][0]["status"], "expired")
        self.assertTrue(LearningSubscription.objects.filter(pk=expired.pk).exists())
        self.assertTrue(LearningPathParticipation.objects.filter(pk=participation.pk).exists())

    def test_checkout_is_provider_disabled_creates_no_payment_and_never_touches_school_billing(self):
        self.auth()
        before_subscriptions = LearningSubscription.objects.count()
        before_fee_rows = StudentFee.objects.count()
        before_fee_payments = FeePayment.objects.count()
        response = self.client.post(
            f"{BASE}subscriptions/checkout/",
            {"plan_code": "premium"},
            format="json",
        )
        self.assertEqual(response.status_code, 503, response.content)
        self.assertEqual(response.json()["code"], "payment_provider_not_configured")
        self.assertFalse(response.json()["payment_created"])
        self.assertFalse(response.json()["premium_activated"])
        self.assertEqual(LearningSubscription.objects.count(), before_subscriptions)
        self.assertEqual(StudentFee.objects.count(), before_fee_rows)
        self.assertEqual(FeePayment.objects.count(), before_fee_payments)

    def test_only_linked_school_guardian_can_manage_minor_checkout(self):
        minor = Student.objects.create(
            school=self.school,
            first_name="Taylor",
            last_name="Learner",
            admission_number="SUB-MINOR",
            date_of_birth=date(2012, 1, 1),
        )
        minor_user = User.objects.create_user("subscription_minor", password="TestPassword!123")
        minor_profile = LearningProfile.objects.create(
            user=minor_user,
            account_kind="school_student",
            school=self.school,
            student=minor,
            age_band="10_17",
            consent_state="verified",
        )
        guardian_user = User.objects.create_user("subscription_guardian", password="TestPassword!123")
        guardian = GuardianProfile.objects.create(user=guardian_user, school=self.school)
        StudentGuardian.objects.create(student=minor, guardian=guardian, relationship="parent", is_primary=True)

        self.client.force_authenticate(minor_user)
        self_response = self.client.post(
            f"{BASE}subscriptions/checkout/",
            {"plan_code": "premium"},
            format="json",
        )
        self.assertEqual(self_response.status_code, 403)
        self.assertEqual(self_response.json()["code"], "guardian_payer_required")

        before_subscriptions = LearningSubscription.objects.count()
        before_fee_rows = StudentFee.objects.count()
        before_fee_payments = FeePayment.objects.count()
        self.client.force_authenticate(guardian_user)
        guardian_response = self.client.post(
            f"{BASE}subscriptions/checkout/",
            {"plan_code": "premium", "profile_id": minor_profile.pk},
            format="json",
        )
        self.assertEqual(guardian_response.status_code, 503, guardian_response.content)
        self.assertEqual(guardian_response.json()["code"], "payment_provider_not_configured")
        self.assertFalse(guardian_response.json()["payment_created"])
        self.assertEqual(LearningSubscription.objects.count(), before_subscriptions)
        self.assertEqual(StudentFee.objects.count(), before_fee_rows)
        self.assertEqual(FeePayment.objects.count(), before_fee_payments)

        unrelated_guardian = User.objects.create_user("subscription_unlinked_guardian")
        self.client.force_authenticate(unrelated_guardian)
        hidden = self.client.post(
            f"{BASE}subscriptions/checkout/",
            {"plan_code": "premium", "profile_id": minor_profile.pk},
            format="json",
        )
        self.assertEqual(hidden.status_code, 404)
