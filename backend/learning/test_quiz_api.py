import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningActivityEvent,
    LearningProfile,
    LearningQuizAttempt,
    LearningResource,
)
from schools.models import School, Student

User = get_user_model()
QUIZ = {
    "schema_version": 1,
    "questions": [
        {
            "id": "q1", "prompt": "Which number is even?",
            "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}],
            "correct_option_id": "b", "explanation": "Four is divisible by two.",
        },
        {
            "id": "q2", "prompt": "What is 2 + 2?",
            "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}],
            "correct_option_id": "b", "explanation": "Two plus two is four.",
        },
    ],
}


class LearningPracticeQuizApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Quiz School", code="QUIZ")
        self.publisher = User.objects.create_user("quiz_publisher")
        self.user, self.profile = self.make_learner("quiz_learner", "QUIZ-1", self.school)
        self.other_school = School.objects.create(name="Other Quiz School", code="OQUIZ")
        self.other_user, self.other_profile = self.make_learner("other_quiz_learner", "OQUIZ-1", self.other_school)
        self.resource = self.make_resource("Number practice")
        self.url = f"/api/learning/v1/practice/resources/{self.resource.pk}/quiz/"
        self.attempt_url = f"/api/learning/v1/practice/resources/{self.resource.pk}/attempts/"
        self.client.force_authenticate(self.user)

    def make_learner(self, username, admission, school):
        student = Student.objects.create(
            school=school, first_name=username, last_name="Learner",
            admission_number=admission, date_of_birth=date(2010, 5, 5),
        )
        user = User.objects.create_user(username, password="Test!123456")
        profile = LearningProfile.objects.create(
            user=user, account_kind="school_student", school=school,
            student=student, age_band="10_17", consent_state="verified", locale="en",
        )
        return user, profile

    def make_resource(self, title, *, scope="school", school=None, language="en", tier="free", status="published"):
        now = timezone.now()
        return LearningResource.objects.create(
            scope=scope, school=school or (self.school if scope == "school" else None),
            title=title, summary="A short original practice quiz.",
            body="Try these practice questions.", resource_type="interactive",
            practice_quiz=QUIZ, language_code=language, access_tier=tier,
            status=status, reviewed_by=self.publisher, reviewed_at=now,
            published_at=now if status == "published" else None,
        )

    def payload(self, *, key=None, version=None, answers=None):
        return {
            "idempotency_key": str(key or uuid.uuid4()),
            "resource_version": version or self.resource.version,
            "answers": answers or {"q1": "b", "q2": "a"},
        }

    def test_quiz_read_returns_only_current_visible_questions_without_keys(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["resource_version"], self.resource.version)
        serialized = str(response.json())
        self.assertNotIn("correct_option_id", serialized)
        self.assertNotIn("explanation", serialized)
        self.assertEqual(response.json()["quiz"]["questions"][0]["options"][1]["id"], "b")
        catalog = self.client.get(f"/api/learning/v1/catalog/resources/{self.resource.pk}/")
        self.assertEqual(catalog.status_code, 200, catalog.content)
        self.assertNotIn("correct_option_id", str(catalog.json()))
        self.assertNotIn("practice_quiz", catalog.json())

    def test_server_scores_and_records_only_private_outcome_and_completion_evidence(self):
        response = self.client.post(self.attempt_url, self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["correct_count"], 1)
        self.assertEqual(body["question_count"], 2)
        self.assertEqual([row["correct"] for row in body["feedback"]], [True, False])
        self.assertIn("not a Marian exam mark", body["recording_policy"])

        attempt = LearningQuizAttempt.objects.get(profile=self.profile)
        self.assertEqual(attempt.correct_count, 1)
        self.assertNotIn("answers", attempt.__dict__)
        self.assertNotIn("selected_option_id", str(attempt.feedback))
        event = LearningActivityEvent.objects.get(profile=self.profile)
        self.assertEqual(event.event_type, "completed")
        self.assertEqual(event.details, {
            "evidence_type": "validated_practice_quiz",
            "resource_version": self.resource.version,
        })
        self.assertNotIn("correct", str(event.details))
        self.assertNotIn("answers", str(event.details))

        history = self.client.get("/api/learning/v1/activity-events/")
        self.assertEqual(history.status_code, 200, history.content)
        self.assertEqual(history.json()["results"][0]["event_type"], "completed")
        self.assertEqual(history.json()["results"][0]["details"], event.details)

    def test_idempotent_repeat_returns_same_attempt_and_changed_answers_conflict(self):
        key = uuid.uuid4()
        first = self.client.post(self.attempt_url, self.payload(key=key), format="json")
        repeat = self.client.post(self.attempt_url, self.payload(key=key), format="json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(repeat.status_code, 200, repeat.content)
        self.assertEqual(first.json()["attempt_id"], repeat.json()["attempt_id"])
        self.assertEqual(LearningQuizAttempt.objects.filter(profile=self.profile).count(), 1)
        conflict = self.client.post(
            self.attempt_url,
            self.payload(key=key, answers={"q1": "a", "q2": "a"}),
            format="json",
        )
        self.assertEqual(conflict.status_code, 409)

    def test_new_attempt_key_allows_private_practice_retry(self):
        first = self.client.post(self.attempt_url, self.payload(), format="json")
        second = self.client.post(self.attempt_url, self.payload(answers={"q1": "b", "q2": "b"}), format="json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(LearningQuizAttempt.objects.filter(profile=self.profile).count(), 2)
        self.assertEqual(LearningActivityEvent.objects.filter(profile=self.profile, event_type="completed").count(), 2)

    def test_invalid_payloads_and_stale_versions_are_rejected_without_outcomes(self):
        base = self.payload()
        self.assertEqual(self.client.post(self.attempt_url, {**base, "score": 100}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.attempt_url, {**base, "answers": {"q1": "b"}}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.attempt_url, {**base, "answers": {"q1": "forged", "q2": "a"}}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.attempt_url, {**base, "resource_version": self.resource.version + 1}, format="json").status_code, 409)
        self.assertEqual(LearningQuizAttempt.objects.count(), 0)
        self.assertEqual(LearningActivityEvent.objects.count(), 0)

    def test_cross_school_draft_and_premium_resources_remain_hidden(self):
        hidden = self.make_resource("Other school quiz", school=self.other_school)
        premium = self.make_resource("Premium quiz", tier="premium")
        draft = self.make_resource("Draft quiz", status="draft")
        for row in (hidden, premium, draft):
            self.assertEqual(self.client.get(f"/api/learning/v1/practice/resources/{row.pk}/quiz/").status_code, 404)
            result = self.client.post(
                f"/api/learning/v1/practice/resources/{row.pk}/attempts/",
                {"idempotency_key": str(uuid.uuid4()), "resource_version": row.version,
                 "answers": {"q1": "b", "q2": "b"}}, format="json",
            )
            self.assertEqual(result.status_code, 404)
        self.assertEqual(LearningQuizAttempt.objects.count(), 0)

    def test_language_mismatch_fails_closed_until_quiz_content_is_reviewed_in_that_language(self):
        response = self.client.get(self.url + "?lang=sw")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Learning quiz not found.")

    def test_only_learner_owner_can_retrieve_or_submit(self):
        self.client.force_authenticate(self.other_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        denied = self.client.post(self.attempt_url, self.payload(), format="json")
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(LearningQuizAttempt.objects.count(), 0)

    def test_verified_public_learner_can_take_public_quiz_but_not_school_quiz(self):
        public_user = User.objects.create_user("public_quiz_learner")
        now = timezone.now()
        LearningProfile.objects.create(
            user=public_user, account_kind="public_learner", age_band="adult",
            age_verified_at=now, age_verification_source="provider",
            contact_verified_at=now, contact_verification_channel="email",
            consent_state="not_required", locale="en",
        )
        public_resource = self.make_resource("Shared public quiz", scope="public")
        self.client.force_authenticate(public_user)
        public_url = f"/api/learning/v1/practice/resources/{public_resource.pk}/quiz/"
        self.assertEqual(self.client.get(public_url).status_code, 200)
        school_url = f"/api/learning/v1/practice/resources/{self.resource.pk}/quiz/"
        self.assertEqual(self.client.get(school_url).status_code, 404)

    def test_quiz_endpoints_require_an_eligible_learning_profile(self):
        staff = User.objects.create_user("quiz_staff")
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(LearningQuizAttempt.objects.count(), 0)
