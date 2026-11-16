import threading

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from learning.models import (
    LearningAuditEvent,
    LearningContentRevision,
    LearningPath,
    LearningResource,
    LearningResourceTranslation,
)
from schools.models import School, SchoolAdminProfile, TeacherProfile

User = get_user_model()
BASE = "/api/learning/v1/studio/"


class LearningContentGovernanceApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Governance School", code="GOV")
        self.other_school = School.objects.create(name="Other Governance School", code="OGOV")
        self.teacher = self.make_teacher("content_teacher", self.school)
        self.other_teacher = self.make_teacher("other_content_teacher", self.school)
        self.admin = self.make_admin("content_admin", self.school)
        self.deputy = self.make_admin("content_deputy", self.school, deputy=True)
        self.other_admin = self.make_admin("other_school_admin", self.other_school)

    @staticmethod
    def make_teacher(username, school):
        user = User.objects.create_user(username, password="Content!123456")
        TeacherProfile.objects.create(user=user, school=school)
        return user

    @staticmethod
    def make_admin(username, school, deputy=False):
        user = User.objects.create_user(username, password="Content!123456")
        SchoolAdminProfile.objects.create(user=user, school=school, is_deputy=deputy)
        return user

    def auth(self, user):
        self.client.force_authenticate(user)

    def resource_payload(self, **overrides):
        data = {
            "title": "Fractions lesson", "summary": "An original Marian resource.",
            "body": "A short explanation of fractions.", "language_code": "en", "practice_quiz": {},
            "age_min": 10, "age_max": 16, "source_name": "Teacher-created lesson",
            "license_name": "Marian-owned draft", "attribution": "Created by the Marian teacher.",
        }
        data.update(overrides)
        return data

    def path_payload(self, **overrides):
        data = {
            "title": "Fractions path", "description": "A guided school path.",
            "objectives": ["Understand fractions"], "language_code": "en",
            "age_min": 10, "age_max": 16, "source_name": "Teacher-created path",
            "license_name": "Marian-owned draft", "attribution": "Created by the Marian teacher.",
            "items": [{"position": 1, "item_type": "activity", "title": "Think it through",
                       "instructions": "Consider one example.", "completion_rule": "view"}],
        }
        data.update(overrides)
        return data

    def create_resource(self, user=None, **overrides):
        self.auth(user or self.teacher)
        return self.client.post(BASE + "resources/", self.resource_payload(**overrides), format="json")

    def test_only_real_school_teachers_and_full_admins_can_author_in_their_tenant(self):
        response = self.create_resource()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["scope"], "school")
        self.assertEqual(response.json()["school_id"], self.school.pk)
        self.assertEqual(response.json()["author_id"], self.teacher.pk)

        self.auth(self.other_teacher)
        listing = self.client.get(BASE + "resources/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["results"], [])

        foreign = LearningResource.objects.create(
            scope="school", school=self.other_school, title="Foreign draft", author=self.other_admin,
        )
        self.assertEqual(self.client.get(f"{BASE}resources/{foreign.pk}/").status_code, 404)
        self.assertEqual(self.client.post(BASE + "resources/", {**self.resource_payload(), "scope": "public"}, format="json").status_code, 400)

        self.client.force_authenticate(None)
        stranger = User.objects.create_user("unassigned_content_user")
        self.auth(stranger)
        self.assertEqual(self.client.get(BASE + "resources/").status_code, 403)
        self.auth(self.deputy)
        self.assertEqual(self.client.get(BASE + "resources/").status_code, 403)
        staff = User.objects.create_user("platform_staff", is_staff=True)
        self.auth(staff)
        self.assertEqual(self.client.get(BASE + "resources/").status_code, 403)

    def test_external_copied_content_is_rejected(self):
        response = self.create_resource(
            origin="external", resource_type="external_link",
            external_url="https://example.org/open-resource", body="copied third-party text",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("may not copy", response.json()["detail"])
        self.assertEqual(LearningResource.objects.count(), 0)

    def test_resource_draft_versioning_submission_independent_review_and_publish_gate(self):
        created = self.create_resource()
        self.assertEqual(created.status_code, 201, created.content)
        resource_id = created.json()["id"]
        self.assertEqual(created.json()["status"], "draft")
        self.assertEqual(LearningContentRevision.objects.filter(resource_id=resource_id).count(), 1)

        self.auth(self.teacher)
        edited = self.client.patch(f"{BASE}resources/{resource_id}/", {"summary": "Updated explanation."}, format="json")
        self.assertEqual(edited.status_code, 200, edited.content)
        self.assertEqual(edited.json()["version"], 2)
        history = self.client.get(f"{BASE}resources/{resource_id}/revisions/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual([r["version"] for r in history.json()["results"]], [2, 1])

        submitted = self.client.post(f"{BASE}resources/{resource_id}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertEqual(submitted.json()["status"], "in_review")
        own_review = self.client.post(f"{BASE}resources/{resource_id}/review/", {"decision": "approve"}, format="json")
        self.assertEqual(own_review.status_code, 403)

        self.auth(self.admin)
        queue = self.client.get(BASE + "review-queue/")
        self.assertEqual(queue.status_code, 200)
        self.assertEqual([item["id"] for item in queue.json()["resources"]], [resource_id])
        approved = self.client.post(f"{BASE}resources/{resource_id}/review/", {"decision": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(approved.json()["reviewed_by_id"], self.admin.pk)
        gated = self.client.post(f"{BASE}resources/{resource_id}/publish/", {}, format="json")
        self.assertEqual(gated.status_code, 503)
        self.assertEqual(gated.json()["code"], "content_publication_policy_unapproved")
        resource = LearningResource.objects.get(pk=resource_id)
        self.assertEqual(resource.status, "approved")
        self.assertIsNone(resource.published_at)
        self.assertTrue(LearningAuditEvent.objects.filter(action="resource_publication_blocked", target_id=str(resource_id)).exists())

    def test_interactive_quiz_requires_complete_questions_for_review_and_keeps_answer_key_in_revisions(self):
        created = self.create_resource(resource_type="interactive", practice_quiz={"schema_version": 1, "questions": []})
        self.assertEqual(created.status_code, 201, created.content)
        resource_id = created.json()["id"]
        incomplete = self.client.post(f"{BASE}resources/{resource_id}/submit/", {}, format="json")
        self.assertEqual(incomplete.status_code, 400)
        self.assertIn("at least one complete question", incomplete.json()["detail"])

        quiz = {
            "schema_version": 1,
            "questions": [{
                "id": "q1", "prompt": "Which word is a noun?",
                "options": [{"id": "a", "text": "quickly"}, {"id": "b", "text": "river"}],
                "correct_option_id": "b", "explanation": "A river is a thing.",
            }],
        }
        edited = self.client.patch(f"{BASE}resources/{resource_id}/", {"practice_quiz": quiz}, format="json")
        self.assertEqual(edited.status_code, 200, edited.content)
        self.assertEqual(edited.json()["practice_quiz"], quiz)
        revision = LearningContentRevision.objects.filter(resource_id=resource_id).latest("version")
        self.assertEqual(revision.snapshot["practice_quiz"], quiz)

        submitted = self.client.post(f"{BASE}resources/{resource_id}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertEqual(submitted.json()["status"], "in_review")
        self.assertEqual(self.client.post(f"{BASE}resources/{resource_id}/review/", {"decision": "approve"}, format="json").status_code, 403)

        self.auth(self.admin)
        approved = self.client.post(f"{BASE}resources/{resource_id}/review/", {"decision": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["practice_quiz"]["questions"][0]["correct_option_id"], "b")
        blocked = self.client.post(f"{BASE}resources/{resource_id}/publish/", {}, format="json")
        self.assertEqual(blocked.status_code, 503)

    def test_quiz_content_is_rejected_for_non_interactive_resource(self):
        response = self.create_resource(practice_quiz={"schema_version": 1, "questions": []})
        self.assertEqual(response.status_code, 400)
        self.assertIn("only supported for interactive", response.json()["detail"])

    def test_author_cannot_self_approve_even_when_author_is_full_school_admin(self):
        self.auth(self.admin)
        created = self.client.post(BASE + "resources/", self.resource_payload(), format="json")
        self.assertEqual(created.status_code, 201, created.content)
        content_id = created.json()["id"]
        self.assertEqual(self.client.post(f"{BASE}resources/{content_id}/submit/", {}, format="json").status_code, 200)
        own_review = self.client.post(f"{BASE}resources/{content_id}/review/", {"decision": "approve"}, format="json")
        self.assertEqual(own_review.status_code, 403)
        self.assertEqual(LearningResource.objects.get(pk=content_id).status, "in_review")

    def test_submission_requires_provenance_rights_attribution_valid_language_and_age_range(self):
        created = self.create_resource(source_name="", license_name="", attribution="")
        self.assertEqual(created.status_code, 201, created.content)
        content_id = created.json()["id"]
        response = self.client.post(f"{BASE}resources/{content_id}/submit/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(LearningResource.objects.get(pk=content_id).status, "draft")
        invalid_age = self.create_resource(title="Invalid age", age_min=18, age_max=10)
        self.assertEqual(invalid_age.status_code, 400)

    def test_path_items_only_allow_published_scoped_resources_and_noncompleting_rule(self):
        self.auth(self.teacher)
        created = self.client.post(BASE + "paths/", self.path_payload(), format="json")
        self.assertEqual(created.status_code, 201, created.content)
        path_id = created.json()["id"]
        self.assertEqual(created.json()["origin"], "teacher")
        self.assertEqual(created.json()["items"][0]["completion_rule"], "view")
        invalid = self.client.patch(f"{BASE}paths/{path_id}/", {
            "items": [{"position": 1, "item_type": "activity", "title": "Task", "instructions": "Do it.", "completion_rule": "click"}],
        }, format="json")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(LearningPath.objects.get(pk=path_id).version, 1)

    def test_content_editors_can_set_access_tier_and_revisions_capture_tier_changes(self):
        self.auth(self.teacher)
        resource_response = self.client.post(
            BASE + "resources/", self.resource_payload(access_tier="premium"), format="json",
        )
        self.assertEqual(resource_response.status_code, 201, resource_response.content)
        resource_id = resource_response.json()["id"]
        self.assertEqual(resource_response.json()["access_tier"], "premium")
        self.assertEqual(
            LearningContentRevision.objects.filter(resource_id=resource_id).first().snapshot["access_tier"],
            "premium",
        )
        resource_edit = self.client.patch(
            f"{BASE}resources/{resource_id}/", {"access_tier": "free"}, format="json",
        )
        self.assertEqual(resource_edit.status_code, 200, resource_edit.content)
        self.assertEqual(resource_edit.json()["access_tier"], "free")
        self.assertEqual(
            LearningContentRevision.objects.filter(resource_id=resource_id).first().snapshot["access_tier"],
            "free",
        )
        invalid_resource = self.client.patch(
            f"{BASE}resources/{resource_id}/", {"access_tier": "enterprise"}, format="json",
        )
        self.assertEqual(invalid_resource.status_code, 400)

        path_response = self.client.post(
            BASE + "paths/", self.path_payload(access_tier="premium"), format="json",
        )
        self.assertEqual(path_response.status_code, 201, path_response.content)
        path_id = path_response.json()["id"]
        self.assertEqual(path_response.json()["access_tier"], "premium")
        self.assertEqual(
            LearningContentRevision.objects.filter(path_id=path_id).first().snapshot["access_tier"],
            "premium",
        )
        invalid_path = self.client.patch(
            f"{BASE}paths/{path_id}/", {"access_tier": "enterprise"}, format="json",
        )
        self.assertEqual(invalid_path.status_code, 400)

    def test_path_submission_review_and_publication_are_separate_and_gated(self):
        self.auth(self.teacher)
        created = self.client.post(BASE + "paths/", self.path_payload(), format="json")
        self.assertEqual(created.status_code, 201, created.content)
        path_id = created.json()["id"]
        submitted = self.client.post(f"{BASE}paths/{path_id}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertEqual(submitted.json()["status"], "in_review")
        self.auth(self.admin)
        approved = self.client.post(f"{BASE}paths/{path_id}/review/", {"decision": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
        gated = self.client.post(f"{BASE}paths/{path_id}/publish/", {}, format="json")
        self.assertEqual(gated.status_code, 503)
        self.assertEqual(LearningPath.objects.get(pk=path_id).status, "approved")

    def test_translation_is_human_draft_until_separate_school_admin_review(self):
        created = self.create_resource()
        self.assertEqual(created.status_code, 201, created.content)
        resource_id = created.json()["id"]
        translation = self.client.post(f"{BASE}resources/{resource_id}/translations/", {
            "language_code": "sw", "title": "Somo la sehemu", "summary": "Muhtasari.", "body": "Maelezo.",
        }, format="json")
        self.assertEqual(translation.status_code, 201, translation.content)
        translation_id = translation.json()["id"]
        self.assertEqual(translation.json()["translation_source"], "human")
        self.assertEqual(translation.json()["review_state"], "draft")

        submitted = self.client.post(f"{BASE}resources/{resource_id}/translations/{translation_id}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json()["review_state"], "in_review")
        self.auth(self.admin)
        approved = self.client.post(f"{BASE}resources/{resource_id}/translations/{translation_id}/review/", {"decision": "approve"}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["review_state"], "approved")
        row = LearningResourceTranslation.objects.get(pk=translation_id)
        self.assertEqual(row.reviewed_by_id, self.admin.pk)
        self.assertIsNotNone(row.reviewed_at)

    def test_translator_cannot_approve_own_translation(self):
        created = self.create_resource()
        resource_id = created.json()["id"]
        translation = self.client.post(f"{BASE}resources/{resource_id}/translations/", {
            "language_code": "fr", "title": "Leçon", "summary": "", "body": "Texte.",
        }, format="json")
        translation_id = translation.json()["id"]
        self.client.post(f"{BASE}resources/{resource_id}/translations/{translation_id}/submit/", {}, format="json")
        self.auth(self.admin)
        own_resource = self.client.post(BASE + "resources/", self.resource_payload(), format="json")
        # The admin is not the translator, so their translation review remains independent.
        self.assertEqual(own_resource.status_code, 201)
        self.auth(self.teacher)
        own_review = self.client.post(f"{BASE}resources/{resource_id}/translations/{translation_id}/review/", {"decision": "approve"}, format="json")
        self.assertEqual(own_review.status_code, 403)

    def test_path_translations_require_human_submission_and_independent_review(self):
        self.auth(self.teacher)
        path_response = self.client.post(BASE + "paths/", self.path_payload(), format="json")
        self.assertEqual(path_response.status_code, 201, path_response.content)
        path_id = path_response.json()["id"]
        translation = self.client.post(f"{BASE}paths/{path_id}/translations/", {
            "language_code": "sw", "title": "Njia ya sehemu",
            "description": "Maelezo ya njia.", "objectives": ["Elewa sehemu"],
        }, format="json")
        self.assertEqual(translation.status_code, 201, translation.content)
        translation_id = translation.json()["id"]
        submitted = self.client.post(f"{BASE}paths/{path_id}/translations/{translation_id}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json()["review_state"], "in_review")
        self.auth(self.admin)
        queue = self.client.get(BASE + "review-queue/")
        self.assertIn(translation_id, [row["id"] for row in queue.json()["path_translations"]])
        reviewed = self.client.post(f"{BASE}paths/{path_id}/translations/{translation_id}/review/", {"decision": "approve"}, format="json")
        self.assertEqual(reviewed.status_code, 200, reviewed.content)
        self.assertEqual(reviewed.json()["review_state"], "approved")
        self.assertTrue(LearningContentRevision.objects.filter(path_id=path_id).count() >= 3)

    def test_full_admin_can_retire_existing_school_published_resource(self):
        now = timezone.now()
        resource = LearningResource.objects.create(
            scope="school", school=self.school, title="Old school resource",
            body="Existing reviewed content.", status="published", reviewed_by=self.teacher,
            reviewed_at=now, published_at=now,
        )
        self.auth(self.admin)
        result = self.client.post(f"{BASE}resources/{resource.pk}/archive/", {}, format="json")
        self.assertEqual(result.status_code, 200, result.content)
        resource.refresh_from_db()
        self.assertEqual(resource.status, "archived")
        self.assertIsNotNone(resource.retired_at)
        self.assertTrue(LearningAuditEvent.objects.filter(action="resource_retired", target_id=str(resource.pk)).exists())

    def test_malformed_nested_path_item_and_review_decisions_return_400(self):
        self.auth(self.teacher)
        for item_type in ([], {}):
            payload = self.path_payload(items=[{
                "position": 1, "item_type": item_type, "title": "Think",
                "instructions": "Consider this.", "completion_rule": "view",
            }])
            malformed_item = self.client.post(BASE + "paths/", payload, format="json")
            self.assertEqual(malformed_item.status_code, 400, malformed_item.content)

        path_response = self.client.post(BASE + "paths/", self.path_payload(), format="json")
        self.assertEqual(path_response.status_code, 201, path_response.content)
        path_id = path_response.json()["id"]
        self.assertEqual(self.client.post(f"{BASE}paths/{path_id}/submit/", {}, format="json").status_code, 200)
        self.auth(self.admin)
        for decision in ([], {}):
            response = self.client.post(f"{BASE}paths/{path_id}/review/", {"decision": decision}, format="json")
            self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(LearningPath.objects.get(pk=path_id).status, "in_review")

        self.auth(self.teacher)
        resource_response = self.create_resource()
        resource_id = resource_response.json()["id"]
        translation = self.client.post(f"{BASE}resources/{resource_id}/translations/", {
            "language_code": "sw", "title": "Somo", "summary": "", "body": "Maelezo.",
        }, format="json")
        translation_id = translation.json()["id"]
        self.client.post(f"{BASE}resources/{resource_id}/translations/{translation_id}/submit/", {}, format="json")
        self.auth(self.admin)
        for decision in ([], {}):
            response = self.client.post(
                f"{BASE}resources/{resource_id}/translations/{translation_id}/review/",
                {"decision": decision}, format="json",
            )
            self.assertEqual(response.status_code, 400, response.content)
        row = LearningResourceTranslation.objects.get(pk=translation_id)
        self.assertEqual(row.review_state, "in_review")

    def test_translation_edit_resets_review_and_cannot_be_approved_as_stale_submission(self):
        created = self.create_resource()
        resource_id = created.json()["id"]
        translation = self.client.post(f"{BASE}resources/{resource_id}/translations/", {
            "language_code": "sw", "title": "Somo la awali", "summary": "Muhtasari.", "body": "Maelezo.",
        }, format="json")
        self.assertEqual(translation.status_code, 201, translation.content)
        translation_id = translation.json()["id"]
        submitted = self.client.post(f"{BASE}resources/{resource_id}/translations/{translation_id}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200)
        edited = self.client.post(f"{BASE}resources/{resource_id}/translations/", {
            "language_code": "sw", "title": "Somo jipya lisilokaguliwa", "summary": "Muhtasari mpya.", "body": "Maelezo mapya.",
        }, format="json")
        self.assertEqual(edited.status_code, 201, edited.content)
        self.assertEqual(edited.json()["review_state"], "draft")

        self.auth(self.admin)
        stale_review = self.client.post(
            f"{BASE}resources/{resource_id}/translations/{translation_id}/review/",
            {"decision": "approve"}, format="json",
        )
        self.assertEqual(stale_review.status_code, 409, stale_review.content)
        row = LearningResourceTranslation.objects.get(pk=translation_id)
        self.assertEqual(row.title, "Somo jipya lisilokaguliwa")
        self.assertEqual(row.review_state, "draft")
        self.assertIsNone(row.reviewed_by_id)


class TranslationReviewRaceTests(TransactionTestCase):
    """Exercise parent/translation lock ordering on databases with row locks."""

    reset_sequences = True

    def setUp(self):
        self.school = School.objects.create(name="Translation Race School", code="TRRACE")
        self.teacher = LearningContentGovernanceApiTests.make_teacher("translation_race_teacher", self.school)
        self.admin = LearningContentGovernanceApiTests.make_admin("translation_race_admin", self.school)
        self.resource = LearningResource.objects.create(
            scope="school", school=self.school, title="Original lesson", language_code="en",
            author=self.teacher,
        )
        self.translation = LearningResourceTranslation.objects.create(
            resource=self.resource, language_code="sw", title="Submitted title",
            summary="Submitted summary", body="Submitted body.", translator=self.teacher,
            review_state="in_review",
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_edit_committing_while_review_waits_is_not_approved_as_old_text(self):
        edit_holds_parent = threading.Event()
        release_edit = threading.Event()
        review_waiting_for_parent = threading.Event()
        worker_errors = []
        response_box = {}

        def edit_translation():
            close_old_connections()
            try:
                with transaction.atomic():
                    LearningResource.objects.select_for_update().get(pk=self.resource.pk)
                    locked = LearningResourceTranslation.objects.select_for_update().get(pk=self.translation.pk)
                    locked.title = "New unreviewed title"
                    locked.summary = "New unreviewed summary"
                    locked.body = "New unreviewed body."
                    locked.review_state = "draft"
                    locked.reviewed_by = None
                    locked.reviewed_at = None
                    locked.save()
                    edit_holds_parent.set()
                    if not release_edit.wait(timeout=10):
                        raise TimeoutError("Test did not release the translation edit.")
            except Exception as exc:  # surfaced in the main test thread
                worker_errors.append(exc)
            finally:
                connections.close_all()

        def review_translation():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.admin)
                connection = connections["default"]

                def observe_lock(execute, sql, params, many, context):
                    normalized = sql.upper()
                    if "FOR UPDATE" in normalized and "LEARNING_RESOURCE" in normalized:
                        review_waiting_for_parent.set()
                    return execute(sql, params, many, context)

                url = f"{BASE}resources/{self.resource.pk}/translations/{self.translation.pk}/review/"
                with connection.execute_wrapper(observe_lock):
                    response_box["response"] = client.post(url, {"decision": "approve"}, format="json")
            except Exception as exc:  # surfaced in the main test thread
                worker_errors.append(exc)
            finally:
                connections.close_all()

        edit = threading.Thread(target=edit_translation)
        review = threading.Thread(target=review_translation)
        edit.start()
        self.assertTrue(edit_holds_parent.wait(timeout=5), "Translation edit did not lock its parent.")
        review.start()
        try:
            self.assertTrue(review_waiting_for_parent.wait(timeout=5), "Review request did not reach the parent lock.")
        finally:
            release_edit.set()
            edit.join(timeout=10)
            review.join(timeout=10)

        self.assertFalse(edit.is_alive(), "Translation edit worker did not finish.")
        self.assertFalse(review.is_alive(), "Translation review worker did not finish.")
        self.assertEqual(worker_errors, [])
        self.assertEqual(response_box["response"].status_code, 409, response_box["response"].content)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.title, "New unreviewed title")
        self.assertEqual(self.translation.review_state, "draft")
        self.assertIsNone(self.translation.reviewed_by_id)
