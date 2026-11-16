from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningPath,
    LearningPathItem,
    LearningProfile,
    LearningResource,
    SavedLearningItem,
)
from schools.models import School, Student

User = get_user_model()
SAVED_URL = "/api/learning/v1/saved/"


class LearnerSavedItemsApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Saved Items School", code="SAVE")
        self.other_school = School.objects.create(name="Other Saved School", code="OSAV")
        self.student = self.make_student(self.school, "S-001", "Amani")
        self.user = User.objects.create_user("saved_learner", password="SavedLearner!123")
        self.profile = LearningProfile.objects.create(
            user=self.user,
            account_kind="school_student",
            school=self.school,
            student=self.student,
            age_band="10_17",
            consent_state="verified",
            locale="en",
        )
        self.reviewer = User.objects.create_user("saved_reviewer")
        self.resource = self.make_resource("Shared lesson")
        self.school_resource = self.make_resource(
            "School lesson", scope="school", school=self.school,
        )
        self.path = self.make_path("Shared path")

    @staticmethod
    def make_student(school, admission, first_name, dob=date(2010, 5, 5)):
        return Student.objects.create(
            school=school,
            first_name=first_name,
            last_name="Learner",
            admission_number=admission,
            date_of_birth=dob,
        )

    def make_resource(
        self, title, *, scope="public", school=None, language_code="en",
        age_min=None, age_max=None, status="published", reviewed=True,
        body="A safe learning lesson.", storage_key="",
    ):
        now = timezone.now()
        return LearningResource.objects.create(
            scope=scope,
            school=school,
            title=title,
            summary="A useful summary.",
            body=body,
            language_code=language_code,
            age_min=age_min,
            age_max=age_max,
            storage_key=storage_key,
            status=status,
            reviewed_by=self.reviewer if reviewed else None,
            reviewed_at=now if reviewed else None,
            published_at=now if status == "published" else None,
        )

    def make_path(
        self, title, *, scope="public", school=None, language_code="en",
        age_min=None, age_max=None, status="published", reviewed=True,
    ):
        now = timezone.now()
        return LearningPath.objects.create(
            scope=scope,
            school=school,
            title=title,
            description="A structured journey.",
            objectives=["Learn safely"],
            language_code=language_code,
            age_min=age_min,
            age_max=age_max,
            status=status,
            reviewed_by=self.reviewer if reviewed else None,
            reviewed_at=now if reviewed else None,
            published_at=now if status == "published" else None,
        )

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)

    def test_anonymous_and_unassigned_users_cannot_list_or_save(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(SAVED_URL).status_code, 401)
        self.assertEqual(
            self.client.post(SAVED_URL, {"resource_id": self.resource.pk}, format="json").status_code,
            401,
        )
        stranger = User.objects.create_user("saved_stranger")
        self.auth(stranger)
        self.assertEqual(self.client.get(SAVED_URL).status_code, 403)
        self.assertEqual(
            self.client.post(SAVED_URL, {"resource_id": self.resource.pk}, format="json").status_code,
            403,
        )

    def test_save_resource_and_path_and_list_only_the_callers_visible_items(self):
        self.auth()
        saved_resource = self.client.post(
            SAVED_URL, {"resource_id": self.resource.pk}, format="json",
        )
        saved_path = self.client.post(
            SAVED_URL, {"path_id": self.path.pk}, format="json",
        )
        self.assertEqual(saved_resource.status_code, 201, saved_resource.content)
        self.assertEqual(saved_path.status_code, 201, saved_path.content)
        self.assertEqual(saved_resource.json()["item_type"], "resource")
        self.assertEqual(saved_resource.json()["item"]["title"], "Shared lesson")
        self.assertEqual(saved_path.json()["item_type"], "path")
        self.assertEqual(saved_path.json()["item"]["title"], "Shared path")
        self.assertEqual(SavedLearningItem.objects.filter(profile=self.profile).count(), 2)

        listing = self.client.get(SAVED_URL)
        self.assertEqual(listing.status_code, 200, listing.content)
        result_ids = {item["item_id"] for item in listing.json()["results"]}
        self.assertEqual(result_ids, {self.resource.pk, self.path.pk})
        self.assertEqual(len(listing.json()["results"]), 2)
        self.assertFalse(listing.json()["truncated"])
        self.assertTrue(all("storage_key" not in row["item"] for row in listing.json()["results"]))

    def test_saving_is_idempotent_and_returns_existing_record(self):
        self.auth()
        first = self.client.post(SAVED_URL, {"resource_id": self.resource.pk}, format="json")
        second = self.client.post(SAVED_URL, {"resource_id": self.resource.pk}, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(SavedLearningItem.objects.filter(profile=self.profile).count(), 1)

    def test_save_rejects_malformed_or_ambiguous_item_references(self):
        self.auth()
        invalid = [
            {},
            {"resource_id": self.resource.pk, "path_id": self.path.pk},
            {"resource_id": True},
            {"resource_id": 0},
            {"resource_id": "1.2"},
            {"resource_id": "9223372036854775808"},
            {"resource_id": 10**30},
            {"path_id": -1},
            {"resource_id": self.resource.pk, "profile_id": self.profile.pk},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.post(SAVED_URL, payload, format="json")
                self.assertEqual(response.status_code, 400, response.content)
        array_body = self.client.post(SAVED_URL, [self.resource.pk], format="json")
        self.assertEqual(array_body.status_code, 400, array_body.content)
        self.assertEqual(SavedLearningItem.objects.count(), 0)

    def test_only_currently_published_reviewed_in_scope_age_and_language_items_can_be_saved(self):
        other_school_resource = self.make_resource(
            "Other school secret", scope="school", school=self.other_school,
        )
        draft = self.make_resource("Draft", status="draft")
        unreviewed = self.make_resource("Unreviewed", reviewed=False)
        too_old = self.make_resource("Wrong age", age_min=18)
        other_school_path = self.make_path(
            "Other school path", scope="school", school=self.other_school,
        )
        draft_path = self.make_path("Draft path", status="draft")
        wrong_language = self.make_resource("Kiswahili only", language_code="sw")
        self.auth()
        for item_type, obj in (
            ("resource_id", other_school_resource),
            ("resource_id", draft),
            ("resource_id", unreviewed),
            ("resource_id", too_old),
            ("path_id", other_school_path),
            ("path_id", draft_path),
            ("resource_id", wrong_language),
        ):
            with self.subTest(item_type=item_type, title=obj.title):
                response = self.client.post(SAVED_URL, {item_type: obj.pk}, format="json")
                self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(SavedLearningItem.objects.count(), 0)

    def test_school_learner_can_save_own_school_content_but_public_learner_cannot(self):
        self.auth()
        allowed = self.client.post(
            SAVED_URL, {"resource_id": self.school_resource.pk}, format="json",
        )
        self.assertEqual(allowed.status_code, 201, allowed.content)

        public_user = User.objects.create_user("public_saved_learner")
        public_profile = LearningProfile.objects.create(
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
        self.assertEqual(self.client.get(SAVED_URL).json()["results"], [])
        denied = self.client.post(
            SAVED_URL, {"resource_id": self.school_resource.pk}, format="json",
        )
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(SavedLearningItem.objects.filter(profile=public_profile).count(), 0)

    def test_other_learner_cannot_read_or_remove_another_profiles_save(self):
        self.auth()
        created = self.client.post(
            SAVED_URL, {"resource_id": self.resource.pk}, format="json",
        )
        self.assertEqual(created.status_code, 201)
        other_student = self.make_student(self.school, "S-002", "Other")
        other_user = User.objects.create_user("other_saved_learner")
        LearningProfile.objects.create(
            user=other_user,
            account_kind="school_student",
            school=self.school,
            student=other_student,
            age_band="10_17",
            consent_state="verified",
        )
        self.auth(other_user)
        self.assertEqual(self.client.get(SAVED_URL).json()["results"], [])
        self.assertEqual(
            self.client.delete(f"{SAVED_URL}{created.json()['id']}/").status_code,
            404,
        )
        # DELETE is an idempotent no-op if this caller never saved that item;
        # it must not remove the other learner's row or reveal that it exists.
        self.assertEqual(
            self.client.delete(SAVED_URL, {"resource_id": self.resource.pk}, format="json").status_code,
            204,
        )
        self.assertEqual(SavedLearningItem.objects.count(), 1)

    def test_remove_is_idempotent_and_works_after_content_becomes_hidden(self):
        self.auth()
        created = self.client.post(
            SAVED_URL, {"resource_id": self.resource.pk}, format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.resource.status = "archived"
        self.resource.save(update_fields=["status"])

        listing = self.client.get(SAVED_URL)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["results"], [])
        saved_id = created.json()["id"]
        self.assertEqual(self.client.delete(f"{SAVED_URL}{saved_id}/").status_code, 204)
        self.assertEqual(self.client.delete(f"{SAVED_URL}{saved_id}/").status_code, 404)
        payload = {"resource_id": self.resource.pk}
        self.assertEqual(self.client.delete(SAVED_URL, payload, format="json").status_code, 204)
        self.assertEqual(self.client.delete(SAVED_URL, payload, format="json").status_code, 204)
        self.assertFalse(SavedLearningItem.objects.filter(profile=self.profile).exists())

        path_save = self.client.post(
            SAVED_URL, {"path_id": self.path.pk}, format="json",
        )
        self.assertEqual(path_save.status_code, 201, path_save.content)
        path_payload = {"path_id": self.path.pk}
        self.assertEqual(self.client.delete(SAVED_URL, path_payload, format="json").status_code, 204)
        self.assertEqual(self.client.delete(SAVED_URL, path_payload, format="json").status_code, 204)

    def test_stale_cross_tenant_and_hidden_path_saves_are_not_serialized(self):
        other_school_resource = self.make_resource(
            "Private resource", scope="school", school=self.other_school,
        )
        stale_path = self.make_path("Path with unavailable resource")
        LearningPathItem.objects.create(
            path=stale_path,
            position=1,
            item_type="resource",
            resource=other_school_resource,
            title="Private path step",
        )
        SavedLearningItem.objects.create(profile=self.profile, resource=other_school_resource)
        SavedLearningItem.objects.create(profile=self.profile, path=stale_path)
        self.auth()
        response = self.client.get(SAVED_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["results"], [])
        self.assertNotIn("Private resource", response.content.decode())
        self.assertNotIn("Private path step", response.content.decode())

    def test_age_or_locale_changes_hide_previously_saved_items(self):
        age_limited = self.make_resource("Teen-only lesson", age_min=13, age_max=17)
        self.auth()
        created = self.client.post(
            SAVED_URL, {"resource_id": age_limited.pk}, format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.student.date_of_birth = date(2000, 1, 1)
        self.student.save(update_fields=["date_of_birth"])
        self.assertEqual(self.client.get(SAVED_URL).status_code, 403)
        self.assertTrue(SavedLearningItem.objects.filter(profile=self.profile).exists())

        # Restore a consistent student age and save an English-only item. A
        # Kiswahili listing must omit it rather than return stale saved content.
        self.student.date_of_birth = date(2010, 5, 5)
        self.student.save(update_fields=["date_of_birth"])
        self.assertEqual(self.client.get(f"{SAVED_URL}?lang=sw").json()["results"], [])

    def test_unsupported_list_filters_are_rejected(self):
        self.auth()
        self.assertEqual(self.client.get(f"{SAVED_URL}?school_id=1").status_code, 400)
        self.assertEqual(self.client.get(f"{SAVED_URL}?lang=not-a-locale!").status_code, 400)

    def test_list_is_bounded_to_two_hundred_results(self):
        self.auth()
        rows = []
        for index in range(205):
            resource = self.make_resource(f"Bounded lesson {index:03}")
            rows.append(SavedLearningItem(profile=self.profile, resource=resource))
        SavedLearningItem.objects.bulk_create(rows)

        response = self.client.get(SAVED_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["results"]), 200)
        self.assertTrue(response.json()["truncated"])
