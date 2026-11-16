import uuid
import threading
from datetime import date

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from learning.models import (
    LearningActivityEvent,
    LearningPath,
    LearningPathItem,
    LearningPathParticipation,
    LearningProfile,
    LearningResource,
)
from schools.models import School, Student

User = get_user_model()
EVENTS_URL = "/api/learning/v1/activity-events/"


class LearningActivityApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Activity School", code="ACT")
        self.publisher = User.objects.create_user("activity_publisher")
        self.user, self.profile = self.make_learner("activity_learner", "ACT-1")
        self.other_user, self.other_profile = self.make_learner("activity_other", "ACT-2")
        self.resource = self.make_resource("Visible lesson")
        self.path = self.make_path("Visible path")
        self.item = LearningPathItem.objects.create(
            path=self.path, position=1, item_type="resource", resource=self.resource,
            title="Read the lesson", instructions="Read and consider the lesson.",
        )

    def make_learner(self, username, admission):
        student = Student.objects.create(
            school=self.school, first_name=username, last_name="Learner",
            admission_number=admission, date_of_birth=date(2010, 5, 5),
        )
        user = User.objects.create_user(username, password="Test!123456")
        profile = LearningProfile.objects.create(
            user=user, account_kind="school_student", school=self.school,
            student=student, age_band="10_17", consent_state="verified", locale="en",
        )
        return user, profile

    def make_resource(self, title, *, scope="public", school=None):
        now = timezone.now()
        return LearningResource.objects.create(
            scope=scope, school=school, title=title, summary="A safe lesson.",
            body="Study this lesson.", language_code="en", status="published",
            reviewed_by=self.publisher, reviewed_at=now, published_at=now,
        )

    def make_path(self, title, *, scope="public", school=None):
        now = timezone.now()
        return LearningPath.objects.create(
            scope=scope, school=school, title=title, description="A learning path.",
            objectives=["Study"], language_code="en", status="published",
            reviewed_by=self.publisher, reviewed_at=now, published_at=now,
        )

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)

    def test_starting_a_visible_path_is_idempotent_and_history_is_owner_private(self):
        self.auth()
        url = f"/api/learning/v1/paths/{self.path.pk}/start/"
        first = self.client.post(url, {}, format="json")
        repeated = self.client.post(url, {}, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(first.json()["id"], repeated.json()["id"])
        self.assertEqual(first.json()["state"], "in_progress")
        self.assertIsNone(first.json()["completed_at"])
        self.assertEqual(LearningPathParticipation.objects.count(), 1)

        listing = self.client.get("/api/learning/v1/participation/paths/")
        self.assertEqual(listing.status_code, 200, listing.content)
        self.assertEqual([row["path_id"] for row in listing.json()["results"]], [self.path.pk])
        self.auth(self.other_user)
        other_listing = self.client.get("/api/learning/v1/participation/paths/")
        self.assertEqual(other_listing.status_code, 200)
        self.assertEqual(other_listing.json()["results"], [])

    def test_path_item_progress_requires_participation_and_uses_idempotency(self):
        self.auth()
        event = {
            "idempotency_key": str(uuid.uuid4()),
            "event_type": "progress",
            "path_item_id": self.item.pk,
            "details": {"checkpoint": "reviewed"},
        }
        denied = self.client.post(EVENTS_URL, event, format="json")
        self.assertEqual(denied.status_code, 409, denied.content)
        started = self.client.post(f"/api/learning/v1/paths/{self.path.pk}/start/", {}, format="json")
        self.assertEqual(started.status_code, 201)
        first = self.client.post(EVENTS_URL, event, format="json")
        repeat = self.client.post(EVENTS_URL, event, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(repeat.status_code, 200, repeat.content)
        self.assertEqual(first.json()["id"], repeat.json()["id"])
        self.assertEqual(LearningActivityEvent.objects.filter(profile=self.profile).count(), 1)
        self.assertIsNotNone(LearningPathParticipation.objects.get(profile=self.profile).last_activity_at)

        altered = {**event, "details": {"checkpoint": "needs_help"}}
        conflict = self.client.post(EVENTS_URL, altered, format="json")
        self.assertEqual(conflict.status_code, 409)

    def test_event_schemas_reject_time_claims_and_client_completion(self):
        self.auth()
        base = {"idempotency_key": str(uuid.uuid4()), "resource_id": self.resource.pk}
        duration = self.client.post(EVENTS_URL, {**base, "event_type": "progress", "duration_seconds": 20, "details": {"checkpoint": "attempted"}}, format="json")
        self.assertEqual(duration.status_code, 400)
        completed = self.client.post(EVENTS_URL, {**base, "event_type": "completed"}, format="json")
        self.assertEqual(completed.status_code, 400)
        self.assertIn("server-verifiable", completed.json()["detail"])
        time_event = self.client.post(EVENTS_URL, {**base, "event_type": "started", "occurred_at": "2001-01-01T00:00:00Z"}, format="json")
        self.assertEqual(time_event.status_code, 400)
        malformed = self.client.post(EVENTS_URL, {**base, "event_type": "progress", "details": {"checkpoint": "clicked"}}, format="json")
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(LearningActivityEvent.objects.count(), 0)

    def test_resource_events_are_created_with_server_time_and_no_duration(self):
        self.auth()
        key = str(uuid.uuid4())
        result = self.client.post(EVENTS_URL, {
            "idempotency_key": key, "event_type": "progress",
            "resource_id": self.resource.pk, "details": {"checkpoint": "understood"},
        }, format="json")
        self.assertEqual(result.status_code, 201, result.content)
        row = LearningActivityEvent.objects.get(profile=self.profile)
        self.assertIsNone(row.duration_seconds)
        self.assertLess(abs((timezone.now() - row.occurred_at).total_seconds()), 10)
        self.assertEqual(row.details, {"checkpoint": "understood"})
        self.auth(self.other_user)
        private_history = self.client.get(EVENTS_URL)
        self.assertEqual(private_history.status_code, 200)
        self.assertEqual(private_history.json()["results"], [])

    def test_oversized_activity_body_is_rejected_before_parsing(self):
        self.auth()
        raw = b'{"padding":"' + (b"x" * 9000) + b'"}'
        response = self.client.generic("POST", EVENTS_URL, data=raw, content_type="application/json")
        self.assertEqual(response.status_code, 413)

    def test_hidden_other_school_path_and_resource_are_concealed(self):
        other_school = School.objects.create(name="Hidden Activity School", code="HIDACT")
        hidden_resource = self.make_resource("Hidden", scope="school", school=other_school)
        hidden_path = self.make_path("Hidden path", scope="school", school=other_school)
        hidden_item = LearningPathItem.objects.create(
            path=hidden_path, position=1, item_type="resource", resource=hidden_resource,
        )
        self.auth()
        missing = self.client.post(f"/api/learning/v1/paths/{hidden_path.pk}/start/", {}, format="json")
        self.assertEqual(missing.status_code, 404)
        result = self.client.post(EVENTS_URL, {
            "idempotency_key": str(uuid.uuid4()), "event_type": "progress",
            "path_item_id": hidden_item.pk, "details": {"checkpoint": "attempted"},
        }, format="json")
        self.assertEqual(result.status_code, 404)

    def test_event_and_participation_endpoints_require_active_learner_identity(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(EVENTS_URL).status_code, 401)
        staff = User.objects.create_user("no_learning_profile")
        self.auth(staff)
        self.assertEqual(self.client.get(EVENTS_URL).status_code, 403)
        self.assertEqual(self.client.post(f"/api/learning/v1/paths/{self.path.pk}/start/", {}, format="json").status_code, 403)


class LearningActivityVisibilityRaceTests(TransactionTestCase):
    """Exercise row-lock ordering on databases that implement SELECT FOR UPDATE."""

    reset_sequences = True

    def setUp(self):
        self.school = School.objects.create(name="Race Activity School", code="RACEACT")
        self.publisher = User.objects.create_user("race_activity_publisher")
        self.user = User.objects.create_user("race_activity_learner")
        student = Student.objects.create(
            school=self.school, first_name="Race", last_name="Learner",
            admission_number="RACE-1", date_of_birth=date(2010, 5, 5),
        )
        self.profile = LearningProfile.objects.create(
            user=self.user, account_kind="school_student", school=self.school,
            student=student, age_band="10_17", consent_state="verified", locale="en",
        )
        now = timezone.now()
        self.path = LearningPath.objects.create(
            scope="public", title="Versioned path", description="A path.",
            objectives=["Learn"], language_code="en", status="published",
            reviewed_by=self.publisher, reviewed_at=now, published_at=now,
        )
        self.item = LearningPathItem.objects.create(
            path=self.path, position=1, item_type="activity", title="Reflect",
        )
        LearningPathParticipation.objects.create(
            profile=self.profile, path=self.path, path_version=1, state="in_progress",
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_event_waits_for_path_version_change_and_rejects_stale_participation(self):
        transition_holds_path = threading.Event()
        release_transition = threading.Event()
        event_waiting_for_path = threading.Event()
        worker_errors = []
        response_box = {}

        def bump_path_version():
            close_old_connections()
            try:
                with transaction.atomic():
                    locked_path = LearningPath.objects.select_for_update().get(pk=self.path.pk)
                    locked_path.version = 2
                    locked_path.save(update_fields=["version"])
                    transition_holds_path.set()
                    if not release_transition.wait(timeout=10):
                        raise TimeoutError("Test did not release the path-version transition.")
            except Exception as exc:  # surfaced in the main test thread
                worker_errors.append(exc)
            finally:
                connections.close_all()

        def record_activity():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.user)
                connection = connections["default"]

                def observe_lock(execute, sql, params, many, context):
                    normalized = sql.upper()
                    if "FOR UPDATE" in normalized and "LEARNING_PATH" in normalized:
                        event_waiting_for_path.set()
                    return execute(sql, params, many, context)

                payload = {
                    "idempotency_key": str(uuid.uuid4()), "event_type": "progress",
                    "path_item_id": self.item.pk, "details": {"checkpoint": "attempted"},
                }
                with connection.execute_wrapper(observe_lock):
                    response_box["response"] = client.post(EVENTS_URL, payload, format="json")
            except Exception as exc:  # surfaced in the main test thread
                worker_errors.append(exc)
            finally:
                connections.close_all()

        transition = threading.Thread(target=bump_path_version)
        event = threading.Thread(target=record_activity)
        transition.start()
        self.assertTrue(transition_holds_path.wait(timeout=5), "Transition did not lock the path.")
        event.start()
        try:
            self.assertTrue(event_waiting_for_path.wait(timeout=5), "Activity request did not reach the path lock.")
        finally:
            release_transition.set()
            transition.join(timeout=10)
            event.join(timeout=10)

        self.assertFalse(transition.is_alive(), "Path transition worker did not finish.")
        self.assertFalse(event.is_alive(), "Activity request worker did not finish.")
        self.assertEqual(worker_errors, [])
        self.assertEqual(response_box["response"].status_code, 409, response_box["response"].content)
        self.assertEqual(LearningActivityEvent.objects.filter(profile=self.profile).count(), 0)
