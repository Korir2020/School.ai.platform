from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import LearningFramework, LearningProfile, LearningPreference, LearningTopic
from schools.models import School, Student

User = get_user_model()
ME_URL = "/api/learning/v1/me/"


class LearnerSelfServiceTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Kiswahili School", code="KSW")
        self.student = Student.objects.create(
            school=self.school,
            first_name="Asha",
            last_name="Learner",
            admission_number="K-001",
            date_of_birth=date(2010, 5, 5),
        )
        self.user = User.objects.create_user("self_learner", password="SelfService!123")
        self.profile = LearningProfile.objects.create(
            user=self.user,
            account_kind="school_student",
            school=self.school,
            student=self.student,
            age_band="10_17",
            consent_state="verified",
        )
        framework = LearningFramework.objects.create(
            name="Kenyan CBC", code="cbc", version="2026",
        )
        self.topic = LearningTopic.objects.create(
            framework=framework,
            code="science",
            name="Science",
        )
        self.inactive_topic = LearningTopic.objects.create(
            framework=framework,
            code="retired-topic",
            name="Retired topic",
            is_active=False,
        )

    def auth(self, user=None):
        self.client.force_authenticate(user or self.user)

    def test_anonymous_cannot_read_or_update_learning_profile(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(ME_URL).status_code, 401)
        self.assertEqual(self.client.patch(ME_URL, {"locale": "sw"}, format="json").status_code, 401)

    def test_user_without_learning_profile_is_denied(self):
        stranger = User.objects.create_user("no_learning_profile", password="NoProfile!123")
        self.auth(stranger)
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, 403)

    def test_get_returns_only_own_minimal_profile_and_safe_preference_defaults(self):
        self.auth()
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["profile"], {
            "account_kind": "school_student",
            "locale": "en",
            "age_band": "10_17",
            "consent_state": "verified",
        })
        self.assertEqual(data["preferences"], {
            "topic_ids": [],
            "preferred_languages": [],
            "preferred_formats": [],
            "preferred_difficulty": "",
            "recommendations_enabled": True,
        })
        self.assertNotIn("school_id", data["profile"])
        self.assertNotIn("student_id", data["profile"])
        self.assertNotIn("date_of_birth", data["profile"])
        self.assertFalse(LearningPreference.objects.filter(profile=self.profile).exists())

    def test_patch_locale_and_all_supported_preference_fields(self):
        self.auth()
        response = self.client.patch(ME_URL, {
            "locale": "SW-ke",
            "preferences": {
                "topic_ids": [self.topic.pk],
                "preferred_languages": ["sw", "en-ke"],
                "preferred_formats": ["video", "article"],
                "preferred_difficulty": "BEGINNER",
                "recommendations_enabled": False,
            },
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["profile"]["locale"], "sw-KE")
        self.assertEqual(data["preferences"]["topic_ids"], [self.topic.pk])
        self.assertEqual(data["preferences"]["preferred_languages"], ["sw", "en-KE"])
        self.assertEqual(data["preferences"]["preferred_formats"], ["video", "article"])
        self.assertEqual(data["preferences"]["preferred_difficulty"], "beginner")
        self.assertFalse(data["preferences"]["recommendations_enabled"])

    def test_partial_preference_update_preserves_omitted_values(self):
        preference = LearningPreference.objects.create(
            profile=self.profile,
            preferred_languages=["sw"],
            preferred_formats=["video"],
            preferred_difficulty="intermediate",
            recommendations_enabled=False,
        )
        preference.topics.add(self.topic)
        self.auth()
        response = self.client.patch(ME_URL, {
            "preferences": {"preferred_difficulty": "advanced"},
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["profile"]["locale"], "en")
        self.assertEqual(response.json()["preferences"]["preferred_languages"], ["sw"])
        self.assertEqual(response.json()["preferences"]["preferred_formats"], ["video"])
        self.assertEqual(response.json()["preferences"]["topic_ids"], [self.topic.pk])
        self.assertFalse(response.json()["preferences"]["recommendations_enabled"])
        self.assertEqual(response.json()["preferences"]["preferred_difficulty"], "advanced")

    def test_empty_patch_and_empty_preference_patch_are_rejected(self):
        self.auth()
        self.assertEqual(self.client.patch(ME_URL, {}, format="json").status_code, 400)
        self.assertEqual(
            self.client.patch(ME_URL, {"preferences": {}}, format="json").status_code,
            400,
        )

    def test_server_owned_identity_fields_cannot_be_changed(self):
        self.auth()
        for payload in (
            {"school_id": 999},
            {"school": 999},
            {"student_id": 999},
            {"student": 999},
            {"account_kind": "public_learner"},
            {"age_band": "adult"},
            {"consent_state": "not_required"},
            {"user_id": 999},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(ME_URL, payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.student_id, self.student.pk)
        self.assertEqual(self.profile.school_id, self.school.pk)
        self.assertEqual(self.profile.account_kind, "school_student")
        self.assertEqual(self.profile.age_band, "10_17")
        self.assertEqual(self.profile.consent_state, "verified")

    def test_invalid_locale_and_unknown_top_level_field_are_rejected(self):
        self.auth()
        for locale in ("fr", "en--KE", "english", ""):
            with self.subTest(locale=locale):
                response = self.client.patch(ME_URL, {"locale": locale}, format="json")
                self.assertEqual(response.status_code, 400)
        response = self.client.patch(ME_URL, {"email": "new@example.test"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_preference_types_or_choices_are_rejected(self):
        self.auth()
        invalid_payloads = [
            {"preferred_languages": "sw"},
            {"preferred_languages": ["sw", "SW"]},
            {"preferred_formats": ["unknown-format"]},
            {"preferred_formats": ["video", "video"]},
            {"preferred_difficulty": "expert"},
            {"recommendations_enabled": "false"},
            {"unsupported": True},
        ]
        for preference_data in invalid_payloads:
            with self.subTest(preference_data=preference_data):
                response = self.client.patch(
                    ME_URL, {"preferences": preference_data}, format="json",
                )
                self.assertEqual(response.status_code, 400)

    def test_unavailable_or_inactive_topic_ids_are_rejected_without_mutation(self):
        self.auth()
        for topic_ids in ([999999], [self.inactive_topic.pk], [self.topic.pk, self.topic.pk], [True]):
            with self.subTest(topic_ids=topic_ids):
                response = self.client.patch(
                    ME_URL, {"preferences": {"topic_ids": topic_ids}}, format="json",
                )
                self.assertEqual(response.status_code, 400)
        self.assertFalse(LearningPreference.objects.filter(profile=self.profile).exists())

    def test_preference_lists_are_bounded(self):
        self.auth()
        response = self.client.patch(ME_URL, {
            "preferences": {"preferred_languages": ["en"] * 11},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(ME_URL, {
            "preferences": {"topic_ids": list(range(1, 52))},
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_each_authenticated_user_receives_only_their_own_profile(self):
        other_school = School.objects.create(name="Other", code="OTHER")
        other_student = Student.objects.create(
            school=other_school,
            first_name="Other",
            last_name="Learner",
            admission_number="O-001",
            date_of_birth=date(2009, 1, 1),
        )
        other_user = User.objects.create_user("other_learner", password="OtherLearner!123")
        LearningProfile.objects.create(
            user=other_user,
            account_kind="school_student",
            school=other_school,
            student=other_student,
            age_band="10_17",
            consent_state="verified",
        )
        self.auth(other_user)
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"]["account_kind"], "school_student")
        self.assertNotIn("school_id", response.json()["profile"])
        self.assertNotIn("student_id", response.json()["profile"])
        self.assertEqual(LearningPreference.objects.count(), 0)

    def test_public_adult_can_manage_own_preferences_without_a_school(self):
        public_user = User.objects.create_user("public_adult", password="PublicAdult!123")
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
        response = self.client.patch(ME_URL, {
            "locale": "sw",
            "preferences": {"preferred_languages": ["sw"]},
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["profile"]["locale"], "sw")
        self.assertNotIn("school_id", response.json()["profile"])

    def test_minor_without_verified_guardian_state_is_denied(self):
        self.profile.consent_state = "pending"
        self.profile.save(update_fields=["consent_state", "updated_at"])
        self.auth()
        self.assertEqual(self.client.get(ME_URL).status_code, 403)

    def test_unknown_age_is_denied_even_if_legacy_consent_flag_says_verified(self):
        unknown_student = Student.objects.create(
            school=self.school, first_name="Unknown", last_name="Age",
            admission_number="K-UNKNOWN", date_of_birth=None,
        )
        unknown_user = User.objects.create_user("unknown_age_profile")
        LearningProfile.objects.create(
            user=unknown_user, account_kind="school_student", school=self.school,
            student=unknown_student, age_band="unknown", consent_state="verified",
        )
        self.auth(unknown_user)
        self.assertEqual(self.client.get(ME_URL).status_code, 403)

    def test_school_managed_under_ten_learner_is_allowed_with_verified_consent(self):
        young_student = Student.objects.create(
            school=self.school, first_name="Young", last_name="Learner",
            admission_number="K-UNDER-10", date_of_birth=date(2018, 1, 1),
        )
        young_user = User.objects.create_user("school_under_ten")
        LearningProfile.objects.create(
            user=young_user, account_kind="school_student", school=self.school,
            student=young_student, age_band="under_10", consent_state="verified",
        )
        self.auth(young_user)
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["profile"]["age_band"], "under_10")

    def test_inactive_student_cannot_use_self_service(self):
        self.student.status = "transferred"
        self.student.save(update_fields=["status"])
        self.auth()
        self.assertEqual(self.client.get(ME_URL).status_code, 403)

    def test_suspended_school_cannot_use_student_self_service(self):
        self.school.is_suspended = True
        self.school.save(update_fields=["is_suspended"])
        self.auth()
        self.assertEqual(self.client.get(ME_URL).status_code, 403)

    def test_school_member_profile_is_not_mistaken_for_a_learner_account(self):
        staff_user = User.objects.create_user("staff_learning_profile")
        LearningProfile.objects.create(
            user=staff_user,
            account_kind="school_member",
            school=self.school,
        )
        self.auth(staff_user)
        self.assertEqual(self.client.get(ME_URL).status_code, 403)
