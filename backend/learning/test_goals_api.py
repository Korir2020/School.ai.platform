from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningGoal,
    LearningPath,
    LearningPathItem,
    LearningProfile,
    LearningResource,
    LearningTopic,
)
from schools.models import School, Student

User = get_user_model()
GOALS_URL = "/api/learning/v1/goals/"


class LearnerGoalApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Goal School", code="GOAL")
        self.other_school = School.objects.create(name="Other Goal School", code="OGOL")
        self.student = self.make_student(self.school, "G-001", "Asha")
        self.user = User.objects.create_user("goal_learner", password="GoalLearner!123")
        self.reviewer = User.objects.create_user("goal_reviewer")
        self.profile = LearningProfile.objects.create(
            user=self.user,
            account_kind="school_student",
            school=self.school,
            student=self.student,
            age_band="10_17",
            consent_state="verified",
            locale="en",
        )
        self.topic = LearningTopic.objects.create(code="goal-science", name="Science")
        self.inactive_topic = LearningTopic.objects.create(
            code="old-topic", name="Old topic", is_active=False,
        )
        now = timezone.now()
        self.public_path = self.make_path("Shared science", scope="public", now=now)
        self.school_path = self.make_path("School science", scope="school", school=self.school, now=now)
        self.other_school_path = self.make_path("Private elsewhere", scope="school", school=self.other_school, now=now)
        self.draft_path = LearningPath.objects.create(
            scope="school", school=self.school, title="Unpublished", status="draft",
        )

    def make_path(self, title, *, scope, school=None, now=None, language_code="en", **fields):
        now = now or timezone.now()
        return LearningPath.objects.create(
            scope=scope,
            school=school,
            title=title,
            status="published",
            language_code=language_code,
            reviewed_by=self.reviewer,
            reviewed_at=now,
            published_at=now,
            **fields,
        )

    @staticmethod
    def make_student(school, admission, first_name):
        return Student.objects.create(
            school=school,
            first_name=first_name,
            last_name="Learner",
            admission_number=admission,
            date_of_birth=date(2010, 5, 5),
        )

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)

    def create_goal(self, **payload):
        self.auth()
        return self.client.post(GOALS_URL, payload, format="json")

    def test_anonymous_and_unassigned_users_cannot_access_goals(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(GOALS_URL).status_code, 401)
        self.assertEqual(
            self.client.post(GOALS_URL, {"title": "Study"}, format="json").status_code,
            401,
        )
        stranger = User.objects.create_user("goal_stranger", password="Stranger!123")
        self.auth(stranger)
        self.assertEqual(self.client.get(GOALS_URL).status_code, 403)

    def test_create_list_and_retrieve_only_own_goal(self):
        created = self.create_goal(
            title="Learn about ecosystems",
            description="Study habitats and food webs.",
            topic_id=self.topic.pk,
            path_id=self.public_path.pk,
            target_date="2027-04-01",
        )
        self.assertEqual(created.status_code, 201, created.content)
        data = created.json()
        self.assertEqual(data["state"], "active")
        self.assertEqual(data["topic"]["id"], self.topic.pk)
        self.assertEqual(data["path"]["id"], self.public_path.pk)
        self.assertEqual(data["target_date"], "2027-04-01")
        goal = LearningGoal.objects.get(pk=data["id"])
        self.assertEqual(goal.profile_id, self.profile.pk)

        self.auth()
        listing = self.client.get(GOALS_URL)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([item["id"] for item in listing.json()["results"]], [goal.pk])
        detail = self.client.get(f"{GOALS_URL}{goal.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["title"], "Learn about ecosystems")

    def test_create_defaults_and_null_link_fields_are_supported(self):
        response = self.create_goal(title="General reading")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["state"], "active")
        self.assertIsNone(response.json()["topic"])
        self.assertIsNone(response.json()["path"])
        self.assertIsNone(response.json()["target_date"])

    def test_create_rejects_missing_empty_or_overlong_fields_and_client_state(self):
        self.auth()
        invalid = [
            {},
            {"title": "   "},
            {"title": "x" * 201},
            {"title": "Valid", "description": "x" * 5001},
            {"title": "Valid", "state": "completed"},
            {"title": "Valid", "profile_id": self.profile.pk},
            {"title": "Valid", "school_id": self.school.pk},
        ]
        for payload in invalid:
            with self.subTest(payload=list(payload.keys())):
                response = self.client.post(GOALS_URL, payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(LearningGoal.objects.count(), 0)

    def test_target_date_must_be_iso_date_or_null(self):
        self.auth()
        for target_date in ("tomorrow", "2027-02-30", "20270201", 20270201, ""):
            with self.subTest(target_date=target_date):
                response = self.client.post(
                    GOALS_URL,
                    {"title": "Study", "target_date": target_date},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
        valid = self.client.post(
            GOALS_URL,
            {"title": "Study", "target_date": None},
            format="json",
        )
        self.assertEqual(valid.status_code, 201, valid.content)

    def test_only_active_topics_and_published_in_scope_paths_can_be_linked(self):
        self.auth()
        invalid_payloads = [
            {"title": "Invalid topic", "topic_id": self.inactive_topic.pk},
            {"title": "Unknown topic", "topic_id": 999999},
            {"title": "Wrong-school path", "path_id": self.other_school_path.pk},
            {"title": "Draft path", "path_id": self.draft_path.pk},
            {"title": "Bad id type", "path_id": True},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(GOALS_URL, payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(LearningGoal.objects.count(), 0)

        valid = self.client.post(
            GOALS_URL,
            {"title": "School journey", "path_id": self.school_path.pk},
            format="json",
        )
        self.assertEqual(valid.status_code, 201, valid.content)
        self.assertEqual(valid.json()["path"]["id"], self.school_path.pk)

    def test_goal_links_require_current_age_language_review_and_path_item_visibility(self):
        adult_topic = LearningTopic.objects.create(
            code="adult-topic", name="Adult topic", age_min=18,
        )
        adult_path = self.make_path("Adults only", scope="public", age_min=18)
        wrong_language_path = self.make_path(
            "Wrong language", scope="public", language_code="fr",
        )
        unreviewed_path = self.make_path("Missing review", scope="public")
        unreviewed_path.reviewed_at = None
        unreviewed_path.save(update_fields=["reviewed_at"])
        empty_resource = LearningResource.objects.create(
            scope="public",
            title="Hidden file-only resource",
            body="",
            language_code="en",
            status="published",
            reviewed_by=self.reviewer,
            reviewed_at=timezone.now(),
            published_at=timezone.now(),
        )
        unsafe_path = self.make_path("Unsafe item", scope="public")
        LearningPathItem.objects.create(
            path=unsafe_path,
            position=1,
            item_type="resource",
            resource=empty_resource,
        )

        self.auth()
        invalid_links = [
            {"title": "Age-hidden topic", "topic_id": adult_topic.pk},
            {"title": "Age-hidden path", "path_id": adult_path.pk},
            {"title": "Wrong-language path", "path_id": wrong_language_path.pk},
            {"title": "Unreviewed path", "path_id": unreviewed_path.pk},
            {"title": "Unsafe linked item", "path_id": unsafe_path.pk},
        ]
        for payload in invalid_links:
            with self.subTest(payload=payload):
                response = self.client.post(GOALS_URL, payload, format="json")
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(LearningGoal.objects.count(), 0)

    def test_stale_age_hidden_goal_links_are_omitted_from_detail_and_list(self):
        adult_topic = LearningTopic.objects.create(
            code="legacy-adult-topic", name="Legacy adult topic", age_min=18,
        )
        adult_path = self.make_path("Legacy adults-only", scope="public", age_min=18)
        goal = LearningGoal.objects.create(
            profile=self.profile,
            title="Legacy hidden links",
            topic=adult_topic,
            path=adult_path,
        )

        self.auth()
        detail = self.client.get(f"{GOALS_URL}{goal.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIsNone(detail.json()["topic"])
        self.assertIsNone(detail.json()["path"])
        listing = self.client.get(GOALS_URL)
        self.assertEqual(listing.status_code, 200)
        row = next(item for item in listing.json()["results"] if item["id"] == goal.pk)
        self.assertIsNone(row["topic"])
        self.assertIsNone(row["path"])

    def test_patch_is_partial_and_terminal_state_timestamps_are_consistent(self):
        created = self.create_goal(title="Math practice", topic_id=self.topic.pk)
        goal_id = created.json()["id"]
        self.auth()
        completed = self.client.patch(
            f"{GOALS_URL}{goal_id}/", {"state": "completed"}, format="json",
        )
        self.assertEqual(completed.status_code, 200, completed.content)
        self.assertEqual(completed.json()["title"], "Math practice")
        self.assertEqual(completed.json()["state"], "completed")
        self.assertIsNotNone(completed.json()["closed_at"])

        reopened = self.client.patch(
            f"{GOALS_URL}{goal_id}/", {"state": "active"}, format="json",
        )
        self.assertEqual(reopened.status_code, 200)
        self.assertIsNone(reopened.json()["closed_at"])

        closed = self.client.patch(
            f"{GOALS_URL}{goal_id}/", {"state": "closed"}, format="json",
        )
        self.assertEqual(closed.status_code, 200)
        self.assertIsNotNone(closed.json()["closed_at"])

    def test_patch_can_clear_links_and_target_date(self):
        created = self.create_goal(
            title="Science goal",
            topic_id=self.topic.pk,
            path_id=self.public_path.pk,
            target_date="2027-01-01",
        )
        self.auth()
        updated = self.client.patch(
            f"{GOALS_URL}{created.json()['id']}/",
            {"topic_id": None, "path_id": None, "target_date": None},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertIsNone(updated.json()["topic"])
        self.assertIsNone(updated.json()["path"])
        self.assertIsNone(updated.json()["target_date"])

    def test_empty_patch_and_invalid_state_are_rejected(self):
        created = self.create_goal(title="Science goal")
        self.auth()
        empty = self.client.patch(f"{GOALS_URL}{created.json()['id']}/", {}, format="json")
        self.assertEqual(empty.status_code, 400)
        invalid = self.client.patch(
            f"{GOALS_URL}{created.json()['id']}/", {"state": "deleted"}, format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_delete_soft_closes_goal_instead_of_erasing_history(self):
        created = self.create_goal(title="Keep record")
        goal_id = created.json()["id"]
        self.auth()
        deleted = self.client.delete(f"{GOALS_URL}{goal_id}/")
        self.assertEqual(deleted.status_code, 204)
        goal = LearningGoal.objects.get(pk=goal_id)
        self.assertEqual(goal.state, "closed")
        self.assertIsNotNone(goal.closed_at)
        self.assertEqual(self.client.delete(f"{GOALS_URL}{goal_id}/").status_code, 204)
        self.assertEqual(LearningGoal.objects.count(), 1)

    def test_another_learner_cannot_read_update_or_delete_goal(self):
        created = self.create_goal(title="Private goal")
        goal_id = created.json()["id"]
        other_student = self.make_student(self.school, "G-002", "Other")
        other_user = User.objects.create_user("other_goal_learner")
        LearningProfile.objects.create(
            user=other_user,
            account_kind="school_student",
            school=self.school,
            student=other_student,
            age_band="10_17",
            consent_state="verified",
        )
        self.auth(other_user)
        self.assertEqual(self.client.get(f"{GOALS_URL}{goal_id}/").status_code, 404)
        self.assertEqual(
            self.client.patch(f"{GOALS_URL}{goal_id}/", {"title": "Steal"}, format="json").status_code,
            404,
        )
        self.assertEqual(self.client.delete(f"{GOALS_URL}{goal_id}/").status_code, 404)
        self.assertEqual(LearningGoal.objects.get(pk=goal_id).title, "Private goal")

    def test_state_filter_is_validated_and_scope_limited(self):
        active = self.create_goal(title="Current")
        goal = LearningGoal.objects.get(pk=active.json()["id"])
        other_user = User.objects.create_user("unrelated_goal_owner")
        other_profile = LearningProfile.objects.create(
            user=other_user,
            account_kind="school_member",
            school=self.school,
        )
        LearningGoal.objects.create(profile=other_profile, title="Other owner's goal")
        self.auth()
        response = self.client.get(f"{GOALS_URL}?state=active")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()["results"]], [goal.pk])
        self.assertEqual(self.client.get(f"{GOALS_URL}?state=invalid").status_code, 400)

    def test_public_adult_can_link_only_shared_published_paths(self):
        public_user = User.objects.create_user("public_goal_user")
        LearningProfile.objects.create(
            user=public_user,
            account_kind="public_learner",
            age_band="adult",
            consent_state="not_required",
            age_verified_at=timezone.now(),
            age_verification_source="provider",
            contact_verified_at=timezone.now(),
            contact_verification_channel="email",
        )
        self.auth(public_user)
        allowed = self.client.post(
            GOALS_URL,
            {"title": "Independent study", "path_id": self.public_path.pk},
            format="json",
        )
        self.assertEqual(allowed.status_code, 201, allowed.content)
        denied = self.client.post(
            GOALS_URL,
            {"title": "Private school path", "path_id": self.school_path.pk},
            format="json",
        )
        self.assertEqual(denied.status_code, 400)

    def test_stale_cross_school_path_reference_is_not_exposed_in_goal_response(self):
        # Model clean is not automatically invoked by direct ORM writes; the API
        # still fails closed if historical/imported data contains a bad link.
        goal = LearningGoal.objects.create(
            profile=self.profile,
            title="Legacy malformed link",
            path=self.other_school_path,
        )
        self.auth()
        response = self.client.get(f"{GOALS_URL}{goal.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["path"])

    def test_inactive_student_and_suspended_school_are_blocked(self):
        self.student.status = "left"
        self.student.save(update_fields=["status"])
        self.auth()
        self.assertEqual(self.client.get(GOALS_URL).status_code, 403)

        self.student.status = "active"
        self.student.save(update_fields=["status"])
        self.school.is_suspended = True
        self.school.save(update_fields=["is_suspended"])
        self.assertEqual(self.client.get(GOALS_URL).status_code, 403)
