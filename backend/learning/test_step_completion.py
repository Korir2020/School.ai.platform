import uuid
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningAuditEvent, LearningPath, LearningPathItem, LearningPathParticipation,
    LearningProfile, LearningQuizAttempt, LearningResource, LearningStepCompletion,
)
from learning.test_quiz_api import QUIZ
from schools.models import School, SchoolAdminProfile, Student, TeacherProfile

User = get_user_model()
ASSIGNED = "learning.step_confirmation_api._teacher_assigned_students"
LIST = "/api/learning/v1/teacher/step-confirmations/"


def answers(*flags):
    out = {}
    for index, question in enumerate(QUIZ["questions"]):
        right = question["correct_option_id"]
        wrong = next(o["id"] for o in question["options"] if o["id"] != right)
        good = flags[index] if index < len(flags) else True
        out[question["id"]] = right if good else wrong
    return out


class StepCompletionTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Step School", code="STEP")
        self.publisher = User.objects.create_user("step_publisher")
        self.user, self.profile = self.make_learner("step_learner", "STEP-1")
        self.student = self.profile.student
        self.resource = self.make_resource("Number practice")
        self.path = self.make_path()
        self.item = LearningPathItem.objects.create(
            path=self.path, position=1, item_type="resource",
            resource=self.resource, completion_rule="quiz_pass")
        self.participation = LearningPathParticipation.objects.create(
            profile=self.profile, path=self.path,
            path_version=self.path.version, state="in_progress")
        self.teacher_user = User.objects.create_user("step_teacher", password="TeacherPass!123")
        TeacherProfile.objects.create(user=self.teacher_user, school=self.school)

    def make_learner(self, username, admission):
        student = Student.objects.create(
            school=self.school, first_name=username, last_name="Learner",
            admission_number=admission, date_of_birth=date(2010, 5, 5))
        user = User.objects.create_user(username, password="Test!123456")
        profile = LearningProfile.objects.create(
            user=user, account_kind="school_student", school=self.school,
            student=student, age_band="10_17", consent_state="verified", locale="en")
        return user, profile

    def make_resource(self, title, scope="school"):
        now = timezone.now()
        return LearningResource.objects.create(
            scope=scope, school=self.school if scope == "school" else None,
            title=title, summary="A short original practice quiz.",
            body="Try these practice questions.", resource_type="interactive",
            practice_quiz=QUIZ, language_code="en", access_tier="free",
            status="published", reviewed_by=self.publisher, reviewed_at=now,
            published_at=now)

    def make_path(self, scope="school"):
        now = timezone.now()
        return LearningPath.objects.create(
            scope=scope, school=self.school if scope == "school" else None,
            title="Number path", language_code="en", access_tier="free",
            status="published", reviewed_by=self.publisher, reviewed_at=now,
            published_at=now)

    def submit(self, user, resource, *flags, key=None):
        self.client.force_authenticate(user)
        return self.client.post(
            f"/api/learning/v1/practice/resources/{resource.pk}/attempts/",
            {"idempotency_key": str(key or uuid.uuid4()),
             "resource_version": resource.version, "answers": answers(*flags)},
            format="json")

    def assigned(self, yes=True):
        return patch(ASSIGNED, side_effect=lambda teacher: (
            Student.objects.filter(pk=self.student.pk) if yes else Student.objects.none()))

    def teacher_get(self, yes=True):
        self.client.force_authenticate(self.teacher_user)
        with self.assigned(yes):
            return self.client.get(LIST)

    def decide(self, row, decision, user=None, yes=True):
        self.client.force_authenticate(user or self.teacher_user)
        with self.assigned(yes):
            return self.client.post(f"{LIST}{row.pk}/decision/", {"decision": decision}, format="json")

    def passed_row(self):
        self.assertEqual(self.submit(self.user, self.resource).status_code, 201)
        return LearningStepCompletion.objects.get()

    # evidence is not completion
    def test_pass_awaits_teacher_and_never_completes_the_path(self):
        row = self.passed_row()
        self.assertEqual((row.state, row.method), ("awaiting_confirmation", "teacher"))
        self.assertEqual(row.attempt_id, LearningQuizAttempt.objects.get().pk)
        self.participation.refresh_from_db()
        self.assertEqual(self.participation.state, "in_progress")

    def test_failing_score_creates_nothing(self):
        flags = [False] * len(QUIZ["questions"])
        self.assertEqual(self.submit(self.user, self.resource, *flags).status_code, 201)
        self.assertEqual(LearningStepCompletion.objects.count(), 0)

    def test_custom_pass_mark_is_respected(self):
        flags = [True] + [False] * (len(QUIZ["questions"]) - 1)
        self.submit(self.user, self.resource, *flags)
        attempt = LearningQuizAttempt.objects.get()
        percent = attempt.correct_count * 100 // attempt.question_count
        self.item.completion_rule = f"quiz_pass:{percent + 1}"
        self.item.save()
        self.submit(self.user, self.resource, *flags)
        self.assertEqual(LearningStepCompletion.objects.count(), 0)
        self.item.completion_rule = f"quiz_pass:{percent}"
        self.item.save()
        self.submit(self.user, self.resource, *flags)
        self.assertEqual(LearningStepCompletion.objects.count(), 1)

    def test_view_rule_unstarted_path_and_old_version_create_nothing(self):
        self.item.completion_rule = "view"
        self.item.save()
        self.submit(self.user, self.resource)
        self.item.completion_rule = "quiz_pass"
        self.item.save()
        self.participation.delete()
        self.submit(self.user, self.resource)
        self.participation = LearningPathParticipation.objects.create(
            profile=self.profile, path=self.path, path_version=self.path.version, state="in_progress")
        LearningPath.objects.filter(pk=self.path.pk).update(version=self.path.version + 1)
        self.submit(self.user, self.resource)
        self.assertEqual(LearningStepCompletion.objects.count(), 0)

    def test_replayed_submission_does_not_duplicate(self):
        key = uuid.uuid4()
        self.assertEqual(self.submit(self.user, self.resource, key=key).status_code, 201)
        self.assertEqual(self.submit(self.user, self.resource, key=key).status_code, 200)
        self.assertEqual(LearningStepCompletion.objects.count(), 1)

    # teacher side
    def test_teacher_lists_awaiting_steps_without_scores_or_answers(self):
        self.passed_row()
        response = self.teacher_get()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(set(response.json()["results"][0]), {
            "id", "student_name", "resource_title", "path_id",
            "item_position", "state", "met_pass_mark_at"})
        text = str(response.json()).lower()
        for banned in ("correct", "score", "answer", "feedback"):
            self.assertNotIn(banned, text)

    def test_unassigned_teacher_sees_and_decides_nothing(self):
        row = self.passed_row()
        self.assertEqual(self.teacher_get(yes=False).json()["results"], [])
        self.assertEqual(self.decide(row, "confirm", yes=False).status_code, 404)
        row.refresh_from_db()
        self.assertEqual(row.state, "awaiting_confirmation")

    def test_teacher_confirms_once_and_it_is_audited(self):
        row = self.passed_row()
        self.assertEqual(self.decide(row, "confirm").status_code, 200)
        row.refresh_from_db()
        self.assertEqual((row.state, row.decided_by_id), ("confirmed", self.teacher_user.pk))
        self.assertEqual(self.decide(row, "reject").status_code, 409)
        self.assertEqual(LearningAuditEvent.objects.filter(
            action="step_completion_confirmed").count(), 1)

    def test_rejected_step_returns_to_awaiting_after_new_pass(self):
        row = self.passed_row()
        self.assertEqual(self.decide(row, "reject").status_code, 200)
        self.submit(self.user, self.resource)
        row.refresh_from_db()
        self.assertEqual((row.state, row.decided_by_id), ("awaiting_confirmation", None))

    def test_bad_decision_and_other_roles_are_refused(self):
        row = self.passed_row()
        self.assertEqual(self.decide(row, "maybe").status_code, 400)
        self.assertEqual(self.decide(row, "confirm", user=self.user).status_code, 403)
        admin = User.objects.create_user("step_admin", password="SchoolAdmin!123")
        SchoolAdminProfile.objects.create(user=admin, school=self.school, is_deputy=False)
        self.assertEqual(self.decide(row, "confirm", user=admin).status_code, 403)
        row.refresh_from_db()
        self.assertEqual(row.state, "awaiting_confirmation")

    # independent learners
    def make_public(self):
        user = User.objects.create_user("public_step_learner", password="Test!123456")
        profile = LearningProfile.objects.create(
            user=user, account_kind="public_learner", age_band="adult",
            consent_state="not_required", age_verified_at=timezone.now(),
            age_verification_source="provider", contact_verified_at=timezone.now(),
            contact_verification_channel="email", locale="en")
        resource = self.make_resource("Public practice", scope="public")
        path = self.make_path(scope="public")
        LearningPathItem.objects.create(path=path, position=1, item_type="resource",
                                        resource=resource, completion_rule="quiz_pass")
        LearningPathParticipation.objects.create(
            profile=profile, path=path, path_version=path.version, state="in_progress")
        return user, resource

    def test_independent_learner_is_verified_by_repeat_practice_on_a_later_day(self):
        user, resource = self.make_public()
        self.assertEqual(self.submit(user, resource).status_code, 201)
        row = LearningStepCompletion.objects.get()
        self.assertEqual((row.state, row.method), ("awaiting_confirmation", "repeat_practice"))
        self.assertEqual(self.teacher_get().json()["results"], [])
        self.submit(user, resource)
        row.refresh_from_db()
        self.assertEqual(row.state, "awaiting_confirmation")
        LearningStepCompletion.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(days=1))
        self.submit(user, resource)
        row.refresh_from_db()
        self.assertEqual((row.state, row.decided_by_id), ("confirmed", None))

    @override_settings(LEARNING_INDEPENDENT_REPEAT_VERIFICATION=False)
    def test_repeat_verification_can_be_switched_off(self):
        user, resource = self.make_public()
        self.submit(user, resource)
        row = LearningStepCompletion.objects.get()
        self.assertEqual((row.state, row.method), ("awaiting_confirmation", "teacher"))
