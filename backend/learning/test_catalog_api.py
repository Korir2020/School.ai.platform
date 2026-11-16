from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningFramework,
    LearningPath,
    LearningPathItem,
    LearningProfile,
    LearningResource,
    LearningResourceTranslation,
    LearningTopic,
)
from schools.models import School, Student

User = get_user_model()
CATALOG = "/api/learning/v1/catalog/"


class LearnerCatalogApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Catalog School", code="CAT")
        self.other_school = School.objects.create(name="Other Catalog", code="OCAT")
        self.student = Student.objects.create(
            school=self.school,
            first_name="Nia",
            last_name="Learner",
            admission_number="C-001",
            date_of_birth=date(2010, 5, 5),
        )
        self.user = User.objects.create_user("catalog_learner", password="Catalog!123")
        self.profile = LearningProfile.objects.create(
            user=self.user,
            account_kind="school_student",
            school=self.school,
            student=self.student,
            age_band="10_17",
            consent_state="verified",
            locale="en",
        )
        self.reviewer = User.objects.create_user("catalog_reviewer")
        self.framework = LearningFramework.objects.create(
            name="CBC", code="cbc", version="2026",
        )
        self.topic = LearningTopic.objects.create(
            framework=self.framework,
            code="science",
            name="Science",
            localized_names={"sw": "Sayansi"},
            age_min=13,
            age_max=17,
        )
        self.resource = self.make_resource(
            "Safe science lesson", scope="public", body="<p>Read about plants.</p>",
            age_min=13, age_max=17, language_code="en",
        )
        self.resource.topics.add(self.topic)
        self.resource.frameworks.add(self.framework)

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)

    def make_resource(
        self, title, *, scope="public", school=None, body="A text lesson.",
        language_code="en", age_min=None, age_max=None, resource_type="lesson",
        status="published", reviewed=True, origin="marian", license_name="",
        rights_notes="", external_url="", storage_key="",
    ):
        now = timezone.now()
        return LearningResource.objects.create(
            scope=scope,
            school=school,
            title=title,
            summary="A useful summary.",
            body=body,
            resource_type=resource_type,
            origin=origin,
            license_name=license_name,
            rights_notes=rights_notes,
            external_url=external_url,
            storage_key=storage_key,
            language_code=language_code,
            age_min=age_min,
            age_max=age_max,
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

    def test_anonymous_and_unassigned_users_cannot_browse(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{CATALOG}topics/").status_code, 401)
        stranger = User.objects.create_user("catalog_stranger")
        self.auth(stranger)
        self.assertEqual(self.client.get(f"{CATALOG}resources/").status_code, 403)

    def test_topics_use_active_frameworks_localized_labels_and_age_gate(self):
        self.auth()
        response = self.client.get(f"{CATALOG}topics/?lang=sw")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["language"], "sw")
        topic = next(row for row in response.json()["results"] if row["id"] == self.topic.pk)
        self.assertEqual(topic["name"], "Sayansi")
        self.assertEqual(topic["canonical_name"], "Science")

        inactive_framework = LearningFramework.objects.create(
            name="Retired", code="retired", version="1", is_active=False,
        )
        hidden = LearningTopic.objects.create(
            framework=inactive_framework, code="hidden", name="Hidden",
        )
        LearningTopic.objects.create(
            code="too-young", name="Too young", age_min=5, age_max=10,
        )
        ids = {row["id"] for row in response.json()["results"]}
        self.assertNotIn(hidden.pk, ids)
        self.assertNotIn(LearningTopic.objects.get(code="too-young").pk, ids)

    def test_resource_list_and_detail_are_scoped_published_reviewed_and_sanitized(self):
        own_private = self.make_resource(
            "School-only lesson", scope="school", school=self.school,
        )
        other_private = self.make_resource(
            "Other-school secret", scope="school", school=self.other_school,
        )
        unreviewed = self.make_resource("Not reviewed", reviewed=False)
        self.make_resource("Still draft", status="draft")
        retired = self.make_resource("Retired content")
        retired.retired_at = timezone.now()
        retired.save(update_fields=["retired_at"])

        self.auth()
        response = self.client.get(f"{CATALOG}resources/?lang=en")
        self.assertEqual(response.status_code, 200, response.content)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(self.resource.pk, ids)
        self.assertIn(own_private.pk, ids)
        self.assertNotIn(other_private.pk, ids)
        self.assertNotIn(unreviewed.pk, ids)
        self.assertNotIn(retired.pk, ids)

        detail = self.client.get(f"{CATALOG}resources/{self.resource.pk}/?lang=en")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["body"], "Read about plants.")
        self.assertNotIn("storage_key", detail.json())
        self.assertEqual(
            self.client.get(f"{CATALOG}resources/{other_private.pk}/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"{CATALOG}resources/{unreviewed.pk}/").status_code,
            404,
        )

    def test_resource_cap_counts_visible_rows_after_hidden_candidates(self):
        hidden = [
            self.make_resource(f"A hidden {index:03}", body="")
            for index in range(201)
        ]
        for index in range(201):
            self.make_resource(f"Z visible {index:03}", body="Readable lesson")

        self.auth()
        response = self.client.get(f"{CATALOG}resources/?lang=en")
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 200)
        self.assertTrue(payload["truncated"])
        ids = {row["id"] for row in payload["results"]}
        self.assertIn(self.resource.pk, ids)
        self.assertFalse(ids.intersection(item.pk for item in hidden))

    def test_other_school_content_is_never_visible_to_a_school_learner(self):
        private = self.make_resource(
            "Confidential", scope="school", school=self.other_school,
        )
        self.auth()
        self.assertEqual(
            self.client.get(f"{CATALOG}resources/{private.pk}/").status_code,
            404,
        )
        self.assertNotIn(
            private.pk,
            {row["id"] for row in self.client.get(f"{CATALOG}resources/").json()["results"]},
        )

    def test_public_adult_only_sees_shared_public_catalogue(self):
        public_user = User.objects.create_user("public_catalog_user")
        LearningProfile.objects.create(
            user=public_user,
            account_kind="public_learner",
            age_band="adult",
            consent_state="not_required",
            age_verified_at=timezone.now(),
            age_verification_source="provider",
            contact_verified_at=timezone.now(),
            contact_verification_channel="email",
            locale="en",
        )
        self.make_resource("Adult-only 21+", age_min=21)
        self.make_resource("Child-only", age_min=10, age_max=17)
        self.make_resource("Public-adult content", age_min=18)
        private = self.make_resource(
            "School private", scope="school", school=self.school,
        )
        self.auth(public_user)
        response = self.client.get(f"{CATALOG}resources/")
        self.assertEqual(response.status_code, 200)
        titles = {row["title"] for row in response.json()["results"]}
        self.assertIn("Public-adult content", titles)
        self.assertNotIn("Adult-only 21+", titles)
        self.assertNotIn("Child-only", titles)
        self.assertNotIn("School private", titles)
        self.assertNotIn(private.pk, {row["id"] for row in response.json()["results"]})

    def test_unknown_or_inconsistent_student_age_is_denied_protected_catalogue_access(self):
        self.make_resource("All ages lesson")
        self.make_resource("Age-limited", age_min=10, age_max=17)
        unknown_student = Student.objects.create(
            school=self.school,
            first_name="Unknown",
            last_name="Age",
            admission_number="C-002",
            date_of_birth=None,
        )
        unknown_user = User.objects.create_user("unknown_age_learner")
        LearningProfile.objects.create(
            user=unknown_user,
            account_kind="school_student",
            school=self.school,
            student=unknown_student,
            age_band="unknown",
            consent_state="verified",
        )
        self.auth(unknown_user)
        response = self.client.get(f"{CATALOG}resources/")
        self.assertEqual(response.status_code, 403)

        # A changed DOB no longer matching the server-held band is also denied.
        self.student.date_of_birth = date(2000, 1, 1)
        self.student.save(update_fields=["date_of_birth"])
        self.auth()
        response = self.client.get(f"{CATALOG}resources/")
        self.assertEqual(response.status_code, 403)

    def test_only_approved_reviewed_translations_are_used(self):
        self.resource.language_code = "en"
        self.resource.save(update_fields=["language_code"])
        draft = LearningResourceTranslation.objects.create(
            resource=self.resource,
            language_code="sw",
            title="Rasimu",
            summary="Draft summary",
            body="Draft body",
            translation_source="machine_draft",
            review_state="draft",
        )
        self.auth()
        unavailable = self.client.get(f"{CATALOG}resources/?lang=sw")
        self.assertEqual(unavailable.status_code, 200)
        self.assertEqual(unavailable.json()["results"], [])

        draft.review_state = "approved"
        draft.reviewed_by = self.reviewer
        draft.reviewed_at = timezone.now()
        draft.save(update_fields=["review_state", "reviewed_by", "reviewed_at"])
        translated = self.client.get(f"{CATALOG}resources/{self.resource.pk}/?lang=sw")
        self.assertEqual(translated.status_code, 200, translated.content)
        self.assertEqual(translated.json()["title"], "Rasimu")
        self.assertEqual(translated.json()["body"], "Draft body")
        self.assertEqual(translated.json()["display_language"], "sw")

    def test_external_resources_need_https_and_documented_rights(self):
        no_rights = self.make_resource(
            "No rights", origin="external", external_url="https://example.test/a",
            body="External body",
        )
        no_https = self.make_resource(
            "Unsafe protocol", origin="external", external_url="http://example.test/a",
            license_name="CC BY 4.0", body="External body",
        )
        allowed = self.make_resource(
            "Licensed external", origin="external", external_url="https://example.test/a",
            license_name="CC BY 4.0", body="External body",
        )
        malformed_marian_link = self.make_resource(
            "Malformed Marian link", external_url="javascript:alert(1)",
            body="Readable text",
        )
        self.auth()
        rows = self.client.get(f"{CATALOG}resources/").json()["results"]
        ids = {row["id"] for row in rows}
        self.assertNotIn(no_rights.pk, ids)
        self.assertNotIn(no_https.pk, ids)
        self.assertNotIn(malformed_marian_link.pk, ids)
        self.assertIn(allowed.pk, ids)
        detail = self.client.get(f"{CATALOG}resources/{allowed.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["external_url"], "https://example.test/a")

    def test_file_only_resources_are_hidden_and_storage_keys_are_never_returned(self):
        file_only = self.make_resource(
            "Private file only", body="", storage_key="private/secret.mp4",
        )
        text_and_file = self.make_resource(
            "Text with private media", body="Readable transcript", storage_key="private/secret.mp4",
        )
        self.auth()
        self.assertEqual(
            self.client.get(f"{CATALOG}resources/{file_only.pk}/").status_code,
            404,
        )
        detail = self.client.get(f"{CATALOG}resources/{text_and_file.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["private_asset_pending"])
        self.assertNotIn("storage_key", detail.json())
        self.assertNotIn("private/secret.mp4", str(detail.json()))

    def test_catalog_filters_validate_and_apply_topic_framework_format_and_query(self):
        other = self.make_resource("Audio story", resource_type="audio")
        other.topics.add(self.topic)
        self.auth()
        response = self.client.get(
            f"{CATALOG}resources/?topic_id={self.topic.pk}&framework=cbc&resource_type=lesson&q=science"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["id"] for row in response.json()["results"]], [self.resource.pk])
        for query in (
            "?topic_id=abc", "?topic_id=999999", "?framework=missing",
            "?resource_type=unknown", "?difficulty=expert", "?unknown=1", "?lang=bad--tag",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f"{CATALOG}resources/{query}").status_code, 400)

    def test_paths_require_review_publication_language_age_and_safe_items(self):
        safe_path = self.make_path(
            "Science journey", scope="school", school=self.school,
            age_min=13, age_max=17,
        )
        safe_path.topics.add(self.topic)
        safe_path.frameworks.add(self.framework)
        LearningPathItem.objects.create(
            path=safe_path,
            position=1,
            item_type="resource",
            resource=self.resource,
            title="First lesson",
            instructions="Read this <b>carefully</b>.",
        )
        other_school_path = self.make_path(
            "Other school path", scope="school", school=self.other_school,
        )
        unreviewed = self.make_path("Unreviewed path", reviewed=False)
        old_path = self.make_path("Wrong language", language_code="sw")
        too_old = self.make_path("Too young", age_min=5, age_max=10)
        self.auth()
        safe_ids = {row["id"] for row in self.client.get(f"{CATALOG}paths/?lang=en").json()["results"]}
        self.assertIn(safe_path.pk, safe_ids)
        self.assertNotIn(other_school_path.pk, safe_ids)
        self.assertNotIn(unreviewed.pk, safe_ids)
        self.assertNotIn(old_path.pk, safe_ids)
        self.assertNotIn(too_old.pk, safe_ids)

        detail = self.client.get(f"{CATALOG}paths/{safe_path.pk}/?lang=en")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["items"][0]["resource"]["id"], self.resource.pk)
        self.assertEqual(detail.json()["items"][0]["instructions"], "Read this carefully.")
        self.assertEqual(
            self.client.get(f"{CATALOG}paths/{other_school_path.pk}/").status_code,
            404,
        )

    def test_paths_with_stale_cross_school_or_unreviewed_resource_items_are_hidden(self):
        bad_path = self.make_path(
            "Bad cross-school contents", scope="school", school=self.school,
        )
        unsafe_resource = self.make_resource(
            "Private other resource", scope="school", school=self.other_school,
        )
        LearningPathItem.objects.create(
            path=bad_path, position=1, item_type="resource", resource=unsafe_resource,
        )
        file_path = self.make_path(
            "Unopenable resource path", scope="school", school=self.school,
        )
        hidden_file = self.make_resource("Only a private file", body="", storage_key="hidden/file.pdf")
        LearningPathItem.objects.create(
            path=file_path, position=1, item_type="resource", resource=hidden_file,
        )
        self.auth()
        rows = self.client.get(f"{CATALOG}paths/").json()["results"]
        path_ids = {row["id"] for row in rows}
        self.assertNotIn(bad_path.pk, path_ids)
        self.assertNotIn(file_path.pk, path_ids)
        self.assertEqual(self.client.get(f"{CATALOG}paths/{bad_path.pk}/").status_code, 404)

    def test_path_cap_counts_visible_rows_after_hidden_candidates(self):
        hidden_resource = self.make_resource("A hidden path resource", body="")
        hidden_paths = []
        for index in range(201):
            path = self.make_path(f"A hidden path {index:03}")
            LearningPathItem.objects.create(
                path=path,
                position=1,
                item_type="resource",
                resource=hidden_resource,
            )
            hidden_paths.append(path)
        visible_paths = [
            self.make_path(f"Z visible path {index:03}")
            for index in range(201)
        ]

        self.auth()
        response = self.client.get(f"{CATALOG}paths/?lang=en")
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 200)
        self.assertTrue(payload["truncated"])
        ids = {row["id"] for row in payload["results"]}
        self.assertTrue(ids.intersection(path.pk for path in visible_paths))
        self.assertFalse(ids.intersection(path.pk for path in hidden_paths))

    def test_public_learner_sees_only_public_paths_and_resources(self):
        public_user = User.objects.create_user("public_paths_user")
        LearningProfile.objects.create(
            user=public_user,
            account_kind="public_learner",
            age_band="adult",
            consent_state="not_required",
            age_verified_at=timezone.now(),
            age_verification_source="provider",
            contact_verified_at=timezone.now(),
            contact_verification_channel="email",
            locale="en",
        )
        public_path = self.make_path("Public path")
        private_path = self.make_path("School path", scope="school", school=self.school)
        self.auth(public_user)
        response = self.client.get(f"{CATALOG}paths/")
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(public_path.pk, ids)
        self.assertNotIn(private_path.pk, ids)
        self.assertEqual(self.client.get(f"{CATALOG}paths/{private_path.pk}/").status_code, 404)

    def test_suspended_school_is_denied_and_unknown_filters_are_rejected(self):
        self.auth()
        self.assertEqual(self.client.get(f"{CATALOG}topics/?node_type=invalid").status_code, 400)
        self.assertEqual(self.client.get(f"{CATALOG}topics/?other=1").status_code, 400)
        self.school.is_suspended = True
        self.school.save(update_fields=["is_suspended"])
        self.assertEqual(self.client.get(f"{CATALOG}topics/").status_code, 403)
        self.assertEqual(self.client.get(f"{CATALOG}resources/{self.resource.pk}/").status_code, 403)
