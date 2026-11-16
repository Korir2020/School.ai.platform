from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningActivityEvent,
    LearningAuditEvent,
    LearningGoal,
    LearningPreference,
    LearningProfile,
    LearningRecommendation,
    LearningResource,
    LearningTopic,
)
from schools.models import School, Student

User = get_user_model()
BASE = "/api/learning/v1/"


class DeterministicRecommendationApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Recommendation School", code="RECO")
        self.other_school = School.objects.create(name="Other Recommendation School", code="ORECO")
        self.reviewer = User.objects.create_user("recommendation_reviewer")
        self.learner = User.objects.create_user("recommendation_learner")
        self.student = Student.objects.create(
            school=self.school, first_name="Amina", last_name="Learner",
            admission_number="REC-1", date_of_birth=date(2010, 2, 1),
        )
        self.profile = LearningProfile.objects.create(
            user=self.learner, account_kind="school_student", school=self.school,
            student=self.student, age_band="10_17", consent_state="verified", locale="en",
        )
        self.preference = LearningPreference.objects.create(profile=self.profile)
        self.interest = LearningTopic.objects.create(code="math-interest", name="Mathematics")
        self.other_topic = LearningTopic.objects.create(code="science-interest", name="Science")
        self.client.force_authenticate(self.learner)

    def make_resource(self, title, *, topic=None, scope="public", school=None,
                      access_tier="free", language="en", resource_type="lesson",
                      difficulty="", age_min=None, age_max=None, status="published"):
        now = timezone.now()
        resource = LearningResource.objects.create(
            scope=scope, school=school, title=title, summary="A learning item.",
            body="Original learning content.", resource_type=resource_type,
            origin="marian", access_tier=access_tier, language_code=language,
            difficulty=difficulty, age_min=age_min, age_max=age_max,
            status=status,
            reviewed_by=self.reviewer if status == "published" else None,
            reviewed_at=now if status == "published" else None,
            published_at=now if status == "published" else None,
        )
        if topic:
            resource.topics.add(topic)
        return resource

    def generate(self, **kwargs):
        return self.client.post(f"{BASE}recommendations/generate/?lang=en", {}, format="json", **kwargs)

    def test_generate_uses_only_selected_topics_goals_preferences_and_recent_activity(self):
        self.preference.topics.add(self.interest)
        self.preference.preferred_formats = ["video"]
        self.preference.preferred_difficulty = "beginner"
        self.preference.preferred_languages = ["en"]
        self.preference.save()
        LearningGoal.objects.create(
            profile=self.profile, title="Explore mathematics", topic=self.interest,
            state="active",
        )
        related_activity = self.make_resource("Earlier mathematics lesson", topic=self.interest)
        LearningActivityEvent.objects.create(
            profile=self.profile, event_type="started", resource=related_activity,
            occurred_at=timezone.now(), details={"ignored": "activity details are not used"},
        )
        target = self.make_resource(
            "Mathematics video", topic=self.interest, resource_type="video",
            difficulty="beginner",
        )
        general = self.make_resource("General starting lesson", topic=self.other_topic)
        premium = self.make_resource("Premium hidden lesson", topic=self.interest, access_tier="premium")
        age_restricted = self.make_resource("Age-restricted lesson", topic=self.interest, age_max=12)
        other_school_item = self.make_resource(
            "Other school lesson", topic=self.interest, scope="school", school=self.other_school,
        )
        draft = self.make_resource("Unreviewed lesson", topic=self.interest, status="draft")

        response = self.generate()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["algorithm_version"], "rules-v1")
        self.assertGreaterEqual(response.json()["active_personalized"], 1)
        audit = LearningAuditEvent.objects.get(
            action="learner_recommendations_generate", target_id=str(self.profile.pk),
        )
        self.assertEqual(audit.safe_details["active"], response.json()["active_personalized"])
        self.assertNotIn("topic_ids", audit.safe_details)
        self.assertNotIn("resource_ids", audit.safe_details)

        inbox = self.client.get(f"{BASE}recommendations/?lang=en")
        self.assertEqual(inbox.status_code, 200, inbox.content)
        results = inbox.json()["results"]
        by_id = {row["item"]["id"]: row for row in results}
        self.assertIn(target.pk, by_id)
        row = by_id[target.pk]
        self.assertEqual(row["recommendation_type"], "personalized")
        self.assertEqual(row["reason_code"], "personalized_rules")
        self.assertEqual(
            set(row["source_signals"]),
            {"interest_match", "goal_topic_match", "recent_topic_activity", "format_match", "difficulty_match", "language_match"},
        )
        self.assertIn("topics you chose", row["explanation"])
        self.assertNotIn("marks", row["source_signals"])
        visible_ids = {entry["item"]["id"] for entry in results}
        self.assertNotIn(premium.pk, visible_ids)
        self.assertNotIn(age_restricted.pk, visible_ids)
        self.assertNotIn(other_school_item.pk, visible_ids)
        self.assertNotIn(draft.pk, visible_ids)
        self.assertIn(general.pk, visible_ids)
        self.assertTrue(LearningRecommendation.objects.filter(
            profile=self.profile, resource=target, reason_code="personalized_rules",
            algorithm_version="rules-v1", state="shown",
        ).exists())

    def test_dismissed_suggestion_is_not_regenerated_and_refresh_is_idempotent(self):
        target = self.make_resource("One suitable resource", topic=self.interest)
        first = self.generate()
        self.assertEqual(first.status_code, 200, first.content)
        row = LearningRecommendation.objects.get(profile=self.profile, resource=target)
        dismissed = self.client.post(
            f"{BASE}recommendations/{row.pk}/response/", {"state": "dismissed"}, format="json",
        )
        self.assertEqual(dismissed.status_code, 200, dismissed.content)
        second = self.generate()
        self.assertEqual(second.status_code, 200, second.content)
        self.assertFalse(LearningRecommendation.objects.filter(
            profile=self.profile, resource=target, state__in=["shown", "accepted"],
            reason_code="personalized_rules",
        ).exists())
        self.assertEqual(
            LearningRecommendation.objects.filter(profile=self.profile, resource=target).count(), 1,
        )

    def test_opt_out_hides_personalized_suggestions_but_preserves_teacher_selected_items(self):
        target = self.make_resource("Teacher suggestion", topic=self.interest)
        unknown_target = self.make_resource("Unrecognized stored item", topic=self.other_topic)
        self.preference.recommendations_enabled = False
        self.preference.save(update_fields=["recommendations_enabled"])
        LearningRecommendation.objects.create(
            profile=self.profile, resource=target, reason_code="teacher_selected",
            explanation="Your teacher selected this.", source_signals=["teacher_curated", "marks"],
            algorithm_version="teacher-v1", state="shown",
        )
        unknown = LearningRecommendation.objects.create(
            profile=self.profile, resource=unknown_target, reason_code="internal_marks_profile",
            explanation="Private marks-derived explanation.", source_signals=["marks", {"secret": True}],
            algorithm_version="legacy", state="shown",
        )
        response = self.generate()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["enabled"])
        self.assertEqual(response.json()["generated"], 0)
        inbox = self.client.get(f"{BASE}recommendations/?lang=en")
        self.assertEqual(inbox.status_code, 200, inbox.content)
        self.assertEqual(len(inbox.json()["results"]), 1)
        self.assertEqual(inbox.json()["results"][0]["recommendation_type"], "teacher")
        self.assertEqual(inbox.json()["results"][0]["source_signals"], ["teacher_curated"])
        self.assertNotIn("marks", str(inbox.json()))
        unknown.refresh_from_db()
        self.assertEqual(unknown.state, "expired")
        self.assertFalse(LearningRecommendation.objects.filter(reason_code="personalized_rules").exists())

    def test_generation_rejects_client_supplied_profile_or_target_inputs(self):
        response = self.client.post(
            f"{BASE}recommendations/generate/?lang=en", {"student_id": self.student.pk}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LearningRecommendation.objects.exists())

    def test_unauthenticated_or_nonlearner_cannot_generate(self):
        self.client.force_authenticate(None)
        anonymous = self.generate()
        self.assertEqual(anonymous.status_code, 401)
        staff = User.objects.create_user("recommendation_staff", is_staff=True)
        self.client.force_authenticate(staff)
        denied = self.generate()
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(LearningRecommendation.objects.exists())

    def test_kiswahili_explanation_uses_safe_localized_reason_copy(self):
        self.profile.locale = "sw"
        self.profile.save(update_fields=["locale"])
        self.preference.topics.add(self.interest)
        target = self.make_resource("Somo la hesabu", topic=self.interest, language="sw")
        response = self.client.post(
            f"{BASE}recommendations/generate/?lang=sw", {}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        inbox = self.client.get(f"{BASE}recommendations/?lang=sw")
        self.assertEqual(inbox.status_code, 200, inbox.content)
        row = next(item for item in inbox.json()["results"] if item["item"]["id"] == target.pk)
        self.assertIn("mada ulizochagua", row["explanation"])
