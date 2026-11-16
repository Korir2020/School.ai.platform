from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningAuditEvent,
    LearningPath,
    LearningProfile,
    LearningRecommendation,
    LearningResource,
    LearningSchoolSettings,
)
from schools.models import (
    AcademicYear,
    ClassLevel,
    Curriculum,
    Enrollment,
    School,
    SchoolAdminProfile,
    Stream,
    Student,
    Subject,
    TeacherAssignment,
    TeacherProfile,
)

User = get_user_model()
BASE = "/api/learning/v1/"


class StaffLearningApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Learning Staff School", code="LSTAFF")
        self.other_school = School.objects.create(name="Other Learning School", code="OLSTAFF")
        self.teacher = User.objects.create_user("learning_teacher", password="Learning!123456")
        self.teacher_profile = TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.admin = User.objects.create_user("learning_admin", password="Learning!123456")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school, is_deputy=False)
        self.deputy = User.objects.create_user("learning_deputy", password="Learning!123456")
        SchoolAdminProfile.objects.create(user=self.deputy, school=self.school, is_deputy=True)
        self.other_teacher = User.objects.create_user("other_learning_teacher")
        TeacherProfile.objects.create(user=self.other_teacher, school=self.other_school)
        self.curriculum = Curriculum.objects.create(name="Test curriculum", code="TLEARN")
        self.level = ClassLevel.objects.create(curriculum=self.curriculum, name="Grade 10", level_number=10)
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        self.stream = Stream.objects.create(school=self.school, class_level=self.level, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Learning science")
        TeacherAssignment.objects.create(
            teacher=self.teacher_profile, school=self.school, subject=self.subject, stream=self.stream,
        )
        self.student = Student.objects.create(
            school=self.school, first_name="Nia", last_name="Learner", admission_number="L-001",
            date_of_birth=date(2010, 5, 5),
        )
        Enrollment.objects.create(
            student=self.student, academic_year=self.year, class_level=self.level, stream=self.stream,
        )
        self.learner = User.objects.create_user("learning_student", password="Learning!123456")
        self.profile = LearningProfile.objects.create(
            user=self.learner, account_kind="school_student", school=self.school,
            student=self.student, age_band="10_17", consent_state="verified", locale="en",
        )
        self.reviewer = User.objects.create_user("learning_reviewer")
        self.resource = self.make_resource("Published free chemistry", school=self.school, scope="school")

    def auth(self, user):
        self.client.force_authenticate(user)

    def make_resource(self, title, *, scope="public", school=None, tier="free", status="published", age_min=None, age_max=None):
        now = timezone.now()
        return LearningResource.objects.create(
            scope=scope, school=school, title=title, summary="A learning resource.",
            body="Original teaching text.", resource_type="lesson", origin="marian",
            access_tier=tier, language_code="en", age_min=age_min, age_max=age_max,
            status=status, reviewed_by=self.reviewer if status in {"approved", "published"} else None,
            reviewed_at=now if status in {"approved", "published"} else None,
            published_at=now if status == "published" else None,
        )

    def test_teacher_progress_list_contains_only_assigned_eligible_learners(self):
        outsider = Student.objects.create(
            school=self.school, first_name="Other", last_name="Stream", admission_number="L-002",
            date_of_birth=date(2010, 3, 1),
        )
        Enrollment.objects.create(
            student=outsider, academic_year=self.year, class_level=self.level,
            stream=Stream.objects.create(school=self.school, class_level=self.level, name="B"),
        )
        outsider_user = User.objects.create_user("unassigned_student")
        LearningProfile.objects.create(
            user=outsider_user, account_kind="school_student", school=self.school,
            student=outsider, age_band="10_17", consent_state="verified",
        )
        self.auth(self.teacher)
        response = self.client.get(f"{BASE}teachers/learners/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["student_id"] for row in response.json()["results"]], [self.student.pk])
        row = response.json()["results"][0]
        self.assertEqual(row["learner_name"], "Nia Learner")
        self.assertNotIn("date_of_birth", row)
        self.assertNotIn("age_band", row)
        self.assertNotIn("account_status", row)
        self.assertNotIn("marks", row)
        self.assertTrue(LearningAuditEvent.objects.filter(action="teacher_assigned_learning_progress_list_read").exists())

    def test_teacher_catalogue_shows_only_published_free_and_allowed_scope_content(self):
        premium = self.make_resource("Premium lesson", school=self.school, scope="school", tier="premium")
        draft = self.make_resource("Private draft", school=self.school, scope="school", status="draft")
        other_school = self.make_resource("Other tenant lesson", school=self.other_school, scope="school")
        shared = self.make_resource("Shared free lesson")
        self.auth(self.teacher)
        response = self.client.get(f"{BASE}teachers/catalog/resources/?lang=en")
        self.assertEqual(response.status_code, 200, response.content)
        titles = {row["title"] for row in response.json()["results"]}
        self.assertIn(self.resource.title, titles)
        self.assertIn(shared.title, titles)
        self.assertNotIn(premium.title, titles)
        self.assertNotIn(draft.title, titles)
        self.assertNotIn(other_school.title, titles)

    def test_teacher_can_recommend_only_visible_published_free_item_to_assigned_learner(self):
        self.auth(self.teacher)
        rejected = self.client.post(
            f"{BASE}teachers/learners/{self.student.pk}/recommendations/",
            {"resource_id": self.make_resource("Not published", school=self.school, scope="school", status="draft").pk},
            format="json",
        )
        self.assertEqual(rejected.status_code, 404)
        response = self.client.post(
            f"{BASE}teachers/learners/{self.student.pk}/recommendations/",
            {"resource_id": self.resource.pk, "explanation": "Explore this when ready."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        recommendation = LearningRecommendation.objects.get(pk=response.json()["id"])
        self.assertEqual(recommendation.profile_id, self.profile.pk)
        self.assertEqual(recommendation.source_signals, ["teacher_curated"])
        self.assertNotIn("marks", recommendation.source_signals)

        self.auth(self.learner)
        inbox = self.client.get(f"{BASE}recommendations/?lang=en")
        self.assertEqual(inbox.status_code, 200, inbox.content)
        self.assertEqual(inbox.json()["results"][0]["item"]["title"], self.resource.title)
        accepted = self.client.post(
            f"{BASE}recommendations/{recommendation.pk}/response/", {"state": "accepted"}, format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        recommendation.refresh_from_db()
        self.assertEqual(recommendation.state, "accepted")

    def test_teacher_cannot_recommend_to_unassigned_or_other_school_learner(self):
        other_student = Student.objects.create(
            school=self.other_school, first_name="Other", last_name="Learner", admission_number="OL-1",
            date_of_birth=date(2010, 1, 1),
        )
        other_user = User.objects.create_user("other_student")
        LearningProfile.objects.create(
            user=other_user, account_kind="school_student", school=self.other_school,
            student=other_student, age_band="10_17", consent_state="verified",
        )
        self.auth(self.teacher)
        response = self.client.post(
            f"{BASE}teachers/learners/{other_student.pk}/recommendations/",
            {"resource_id": self.resource.pk}, format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(LearningRecommendation.objects.exists())

    def test_teacher_can_discover_and_recommend_only_visible_free_learning_paths(self):
        now = timezone.now()
        path = LearningPath.objects.create(
            scope="school", school=self.school, title="School science journey",
            description="A guided science programme.", objectives=["Explore science"],
            language_code="en", access_tier="free", status="published",
            reviewed_by=self.reviewer, reviewed_at=now, published_at=now,
        )
        premium_path = LearningPath.objects.create(
            scope="school", school=self.school, title="Premium journey",
            description="Not for the free catalogue.", objectives=[], language_code="en",
            access_tier="premium", status="published", reviewed_by=self.reviewer,
            reviewed_at=now, published_at=now,
        )
        self.auth(self.teacher)
        catalogue = self.client.get(f"{BASE}teachers/catalog/paths/?lang=en")
        self.assertEqual(catalogue.status_code, 200, catalogue.content)
        ids = {item["id"] for item in catalogue.json()["results"]}
        self.assertIn(path.pk, ids)
        self.assertNotIn(premium_path.pk, ids)
        detail = self.client.get(f"{BASE}teachers/catalog/paths/{path.pk}/?lang=en")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["title"], path.title)
        created = self.client.post(
            f"{BASE}teachers/learners/{self.student.pk}/recommendations/",
            {"path_id": path.pk, "explanation": "Try this guided journey."}, format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.auth(self.learner)
        inbox = self.client.get(f"{BASE}recommendations/?lang=en")
        self.assertEqual(inbox.status_code, 200, inbox.content)
        self.assertEqual(inbox.json()["results"][0]["type"], "path")
        self.assertEqual(inbox.json()["results"][0]["item"]["id"], path.pk)

    def test_full_admin_controls_learning_access_age_and_recommendation_gate(self):
        self.auth(self.deputy)
        denied = self.client.get(f"{BASE}admin/learning-settings/")
        self.assertEqual(denied.status_code, 403)

        self.auth(self.admin)
        saved = self.client.patch(
            f"{BASE}admin/learning-settings/",
            {"teacher_recommendations_enabled": True, "minimum_learner_age": 17, "maximum_learner_age": 18},
            format="json",
        )
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(saved.json()["minimum_learner_age"], 17)
        settings = LearningSchoolSettings.objects.get(school=self.school)
        self.assertEqual(settings.updated_by_id, self.admin.pk)
        self.assertTrue(LearningAuditEvent.objects.filter(action="school_learning_settings_updated").exists())

        self.auth(self.teacher)
        assigned = self.client.get(f"{BASE}teachers/learners/")
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertEqual(assigned.json()["results"], [])

        self.auth(self.admin)
        invalid = self.client.patch(
            f"{BASE}admin/learning-settings/",
            {"minimum_learner_age": 20, "maximum_learner_age": 10}, format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_controls_fail_closed_for_disabled_access_and_conflicting_platform_roles(self):
        self.auth(self.admin)
        changed = self.client.patch(
            f"{BASE}admin/learning-settings/",
            {"learning_access_enabled": False, "teacher_studio_enabled": False}, format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)

        self.auth(self.teacher)
        teacher_list = self.client.get(f"{BASE}teachers/learners/")
        self.assertEqual(teacher_list.status_code, 403)
        learner_user = self.client.get(f"{BASE}me/")
        self.assertEqual(learner_user.status_code, 403)

        superuser = User.objects.create_superuser("learning_platform_super", "super@example.test", "Learning!123456")
        self.auth(superuser)
        self.assertEqual(self.client.get(f"{BASE}admin/learning-settings/").status_code, 403)

        dual = User.objects.create_user("learning_dual")
        SchoolAdminProfile.objects.create(user=dual, school=self.school, is_deputy=False)
        TeacherProfile.objects.create(user=dual, school=self.school)
        self.auth(dual)
        self.assertEqual(self.client.get(f"{BASE}admin/learning-settings/").status_code, 403)

        other_admin = User.objects.create_user("learning_other_admin")
        SchoolAdminProfile.objects.create(user=other_admin, school=self.other_school, is_deputy=False)
        self.auth(other_admin)
        isolated = self.client.get(f"{BASE}admin/learning-settings/")
        self.assertEqual(isolated.status_code, 200, isolated.content)
        self.assertTrue(isolated.json()["learning_access_enabled"])
        self.assertFalse(LearningSchoolSettings.objects.filter(school=self.other_school).exists())

    def test_teacher_studio_switch_also_closes_legacy_individual_summary_route(self):
        LearningSchoolSettings.objects.create(
            school=self.school, learning_access_enabled=True, teacher_studio_enabled=False,
        )
        self.auth(self.teacher)
        listing = self.client.get(f"{BASE}teachers/learners/")
        self.assertEqual(listing.status_code, 403)
        legacy_summary = self.client.get(f"{BASE}teachers/learners/{self.student.pk}/summary/")
        self.assertEqual(legacy_summary.status_code, 404)

    def test_review_queue_read_is_audited_with_aggregate_counts_only(self):
        self.auth(self.admin)
        response = self.client.get(f"{BASE}studio/review-queue/")
        self.assertEqual(response.status_code, 200, response.content)
        event = LearningAuditEvent.objects.get(action="learning_content_review_queue_read")
        self.assertEqual(event.school_id, self.school.pk)
        self.assertEqual(event.safe_details, {
            "resources": 0, "paths": 0,
            "resource_translations": 0, "path_translations": 0,
        })
        self.assertNotIn("title", event.safe_details)
