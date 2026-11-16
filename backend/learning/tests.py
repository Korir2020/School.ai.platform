from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from schools.models import GuardianProfile, School, Student, StudentGuardian

from .models import (
    AIInteraction,
    LearningActivityEvent,
    LearningFramework,
    LearningInvitation,
    LearningPath,
    LearningPathItem,
    LearningProfile,
    LearningRecommendation,
    LearningResource,
    LearningTopic,
    SavedLearningItem,
)


class LearningModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="learner-one", password="not-a-real-secret",
        )
        self.school = School.objects.create(name="North School", code="NORTH")
        self.other_school = School.objects.create(name="South School", code="SOUTH")
        self.student = Student.objects.create(
            school=self.school,
            first_name="Amina",
            last_name="Learner",
            admission_number="N-001",
        )

    def test_public_profile_is_independent_from_school_tenant(self):
        profile = LearningProfile.objects.create(
            user=self.user,
            account_kind="public_learner",
            age_band="adult",
        )
        self.assertIsNone(profile.school_id)
        self.assertIsNone(profile.student_id)
        profile.consent_state = "verified"
        profile.save(update_fields=["consent_state", "updated_at"])

    def test_database_rejects_public_profile_with_school(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LearningProfile.objects.create(
                    user=self.user,
                    account_kind="public_learner",
                    school=self.school,
                )

    def test_school_student_requires_matching_school(self):
        profile = LearningProfile(
            user=self.user,
            account_kind="school_student",
            school=self.other_school,
            student=self.student,
        )
        with self.assertRaises(ValidationError) as error:
            profile.full_clean()
        self.assertIn("school", error.exception.message_dict)

    def test_school_member_can_have_learning_profile_without_student_link(self):
        profile = LearningProfile.objects.create(
            user=self.user,
            account_kind="school_member",
            school=self.school,
        )
        self.assertEqual(profile.school_id, self.school.pk)
        self.assertIsNone(profile.student_id)

    def test_student_can_be_linked_to_at_most_one_learning_profile(self):
        LearningProfile.objects.create(
            user=self.user,
            account_kind="school_student",
            school=self.school,
            student=self.student,
        )
        second_user = get_user_model().objects.create_user(username="learner-two")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LearningProfile.objects.create(
                    user=second_user,
                    account_kind="school_student",
                    school=self.school,
                    student=self.student,
                )

    def test_invitation_cannot_claim_a_student_through_another_school(self):
        invite = LearningInvitation(
            student=self.student,
            school=self.other_school,
            token_hash="a" * 64,
            expires_at=timezone.now() + timedelta(days=1),
            guardian_approval_state="not_required",
        )
        with self.assertRaises(ValidationError) as error:
            invite.full_clean()
        self.assertIn("school", error.exception.message_dict)

    def test_guardian_approval_requires_a_guardian_linked_to_student(self):
        guardian_user = get_user_model().objects.create_user(username="guardian-one")
        guardian = GuardianProfile.objects.create(user=guardian_user, school=self.school)
        StudentGuardian.objects.create(student=self.student, guardian=guardian)
        invite = LearningInvitation(
            student=self.student,
            school=self.school,
            created_by=self.user,
            token_hash="b" * 64,
            expires_at=timezone.now() + timedelta(days=1),
            guardian_approval_state="approved",
            guardian_approved_by=guardian,
            guardian_approved_at=timezone.now(),
        )
        invite.full_clean()

    def test_resource_and_path_scope_constraints_are_additive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LearningResource.objects.create(
                    scope="public", school=self.school, title="Mis-scoped resource",
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LearningPath.objects.create(
                    scope="public", school=self.school, title="Mis-scoped path",
                )

    def test_external_resource_needs_https_source_and_recorded_rights_before_publish(self):
        resource = LearningResource(
            scope="public",
            title="External resource",
            origin="external",
            resource_type="external_link",
            external_url="http://example.org/lesson",
            status="published",
        )
        with self.assertRaises(ValidationError):
            resource.full_clean()
        resource.external_url = "https://example.org/lesson"
        resource.license_name = "CC BY 4.0"
        resource.full_clean()

    def test_learning_topics_can_be_global_or_framework_scoped(self):
        framework = LearningFramework.objects.create(
            name="Kenyan CBC", code="cbc", version="2025",
        )
        topic = LearningTopic.objects.create(
            framework=framework, code="science", name="Science", age_min=8, age_max=14,
        )
        self.assertEqual(topic.framework, framework)
        with self.assertRaises(ValidationError):
            LearningTopic(
                framework=framework, code="bad-range", name="Bad range",
                age_min=15, age_max=10,
            ).full_clean()

    def test_path_item_position_is_unique_within_a_path(self):
        path = LearningPath.objects.create(
            scope="school", school=self.school, title="Science journey",
        )
        resource = LearningResource.objects.create(
            scope="school", school=self.school, title="Lesson one",
        )
        LearningPathItem.objects.create(path=path, position=1, resource=resource)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LearningPathItem.objects.create(path=path, position=1, resource=resource)

    def test_path_item_cannot_add_another_schools_private_resource(self):
        path = LearningPath.objects.create(
            scope="school", school=self.school, title="Local path",
        )
        resource = LearningResource.objects.create(
            scope="school", school=self.other_school, title="Private elsewhere",
        )
        item = LearningPathItem(path=path, position=1, resource=resource)
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_saved_item_requires_exactly_one_target_and_is_unique(self):
        profile = LearningProfile.objects.create(
            user=self.user, account_kind="school_member", school=self.school,
        )
        resource = LearningResource.objects.create(
            scope="school", school=self.school, title="A resource",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SavedLearningItem.objects.create(profile=profile)
        SavedLearningItem.objects.create(profile=profile, resource=resource)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SavedLearningItem.objects.create(profile=profile, resource=resource)

    def test_activity_events_are_idempotent_per_learning_profile(self):
        profile = LearningProfile.objects.create(
            user=self.user, account_kind="school_member", school=self.school,
        )
        resource = LearningResource.objects.create(
            scope="school", school=self.school, title="A resource",
        )
        event = LearningActivityEvent.objects.create(
            profile=profile,
            event_type="started",
            resource=resource,
            occurred_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LearningActivityEvent.objects.create(
                    profile=profile,
                    event_type="completed",
                    resource=resource,
                    occurred_at=timezone.now(),
                    idempotency_key=event.idempotency_key,
                )

    def test_public_profile_cannot_save_or_record_school_private_content(self):
        profile = LearningProfile.objects.create(
            user=self.user, account_kind="public_learner", age_band="adult",
        )
        private_resource = LearningResource.objects.create(
            scope="school", school=self.school, title="Private school resource",
        )
        with self.assertRaises(ValidationError):
            SavedLearningItem(profile=profile, resource=private_resource).full_clean()
        with self.assertRaises(ValidationError):
            LearningActivityEvent(
                profile=profile,
                event_type="started",
                resource=private_resource,
                occurred_at=timezone.now(),
            ).full_clean()
        with self.assertRaises(ValidationError):
            LearningRecommendation(
                profile=profile,
                resource=private_resource,
                reason_code="interest_match",
            ).full_clean()

    def test_ai_usage_table_has_no_prompt_or_response_text_fields(self):
        names = {field.name for field in AIInteraction._meta.get_fields()}
        self.assertNotIn("prompt", names)
        self.assertNotIn("response", names)
        interaction = AIInteraction.objects.create(
            profile=LearningProfile.objects.create(
                user=self.user, account_kind="school_member", school=self.school,
            ),
            purpose="tutor",
            state="blocked",
            estimated_cost=Decimal("0"),
        )
        self.assertEqual(interaction.input_tokens, 0)
