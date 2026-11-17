import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningActivityEvent, LearningPath, LearningPathItem, LearningPathParticipation,
    LearningProfile, LearningQuizAttempt, LearningResource, LearningStepCompletion,
)
from learning.quiz_schema import QuizSchemaError, normalize_practice_quiz
from schools.models import School, Student

User = get_user_model()
EX_QUIZ = {"schema_version": 1, "questions": [
    {"id": "s1", "type": "short_text", "prompt": "Name the capital of Kenya.",
     "accepted_answers": ["Nairobi"], "hint": "It starts with N.",
     "explanation": "Nairobi is the capital."},
    {"id": "n1", "type": "numeric", "prompt": "What is 10 / 4?", "answer": "2.5",
     "tolerance": "0.1", "hint": "Divide ten by four.",
     "explanation": "Ten divided by four is 2.5."},
    {"id": "c1", "prompt": "Which number is even?",
     "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}],
     "correct_option_id": "b", "explanation": "Four is divisible by two."},
]}
WRONG = {"s1": "Mombasa", "n1": "3", "c1": "a"}


class ExerciseApiTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Exercise School", code="EXER")
        self.publisher = User.objects.create_user("ex_publisher")
        student = Student.objects.create(
            school=self.school, first_name="ex_learner", last_name="Learner",
            admission_number="EX-1", date_of_birth=date(2010, 5, 5))
        self.user = User.objects.create_user("ex_learner", password="Test!123456")
        self.profile = LearningProfile.objects.create(
            user=self.user, account_kind="school_student", school=self.school,
            student=student, age_band="10_17", consent_state="verified", locale="en")
        now = timezone.now()
        self.resource = LearningResource.objects.create(
            scope="school", school=self.school, title="Exercises",
            summary="A short original practice set.", body="Try these.",
            resource_type="interactive", practice_quiz=EX_QUIZ, language_code="en",
            access_tier="free", status="published", reviewed_by=self.publisher,
            reviewed_at=now, published_at=now)
        base = f"/api/learning/v1/practice/resources/{self.resource.pk}"
        self.quiz_url, self.attempt_url = f"{base}/quiz/", f"{base}/attempts/"
        self.client.force_authenticate(self.user)

    def submit(self, answers=None, key=None):
        body = {"s1": "Nairobi", "n1": "2.5", "c1": "b"}
        body.update(answers or {})
        return self.client.post(self.attempt_url, {
            "idempotency_key": str(key or uuid.uuid4()),
            "resource_version": self.resource.version, "answers": body}, format="json")

    @staticmethod
    def fb(response, qid):
        return next(i for i in response.json()["feedback"] if i["question_id"] == qid)

    def test_learner_view_hides_every_answer_key(self):
        response = self.client.get(self.quiz_url)
        self.assertEqual(response.status_code, 200, response.content)
        text = str(response.json())
        for secret in ("Nairobi", "2.5", "accepted_answers", "tolerance",
                       "It starts with N", "explanation"):
            self.assertNotIn(secret, text)
        questions = {q["id"]: q for q in response.json()["quiz"]["questions"]}
        self.assertEqual(questions["s1"], {"id": "s1", "type": "short_text",
                         "prompt": "Name the capital of Kenya.", "options": []})
        self.assertEqual(set(questions["c1"]), {"id", "prompt", "options"})

    def test_typed_answers_are_normalised_and_scored_on_the_server(self):
        response = self.submit({"s1": "  nAiRoBi  ", "n1": "2.55"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.json()["correct_count"], response.json()["question_count"]), (3, 3))
        self.assertEqual(self.fb(response, "s1")["accepted_answer"], "Nairobi")
        self.assertEqual(self.submit({"n1": 2.5}).json()["correct_count"], 3)

    def test_numeric_tolerance_boundary(self):
        for value, expected in (("2.4", True), ("2.6", True), ("2.39", False), ("2.61", False)):
            with self.subTest(value=value):
                self.assertEqual(self.fb(self.submit({"n1": value}), "n1")["correct"], expected)

    def test_first_wrong_attempt_gives_a_hint_but_not_the_answer(self):
        response = self.submit(WRONG)
        self.assertEqual(response.json()["correct_count"], 0)
        self.assertEqual(self.fb(response, "s1"),
                         {"question_id": "s1", "correct": False, "hint": "It starts with N."})
        self.assertEqual(self.fb(response, "n1"),
                         {"question_id": "n1", "correct": False, "hint": "Divide ten by four."})

    def test_second_submission_reveals_the_answer_and_retries_stay_open(self):
        self.submit(WRONG)
        second = self.fb(self.submit(WRONG), "s1")
        self.assertEqual(second["accepted_answer"], "Nairobi")
        self.assertEqual(second["explanation"], "Nairobi is the capital.")
        self.assertNotIn("hint", second)
        self.assertEqual(self.submit().json()["correct_count"], 3)
        self.assertEqual(LearningQuizAttempt.objects.count(), 3)

    def test_malformed_answers_are_rejected_and_nothing_is_stored(self):
        for bad in ({"s1": ""}, {"s1": "   "}, {"s1": 12}, {"s1": "x" * 201},
                    {"n1": "abc"}, {"n1": True}, {"n1": ""}, {"n1": "1e999"}, {"c1": "zzz"}):
            with self.subTest(bad=bad):
                self.assertEqual(self.submit(bad).status_code, 400)
        self.assertEqual(LearningQuizAttempt.objects.count(), 0)

    def test_replay_returns_the_same_attempt_and_conflicts_are_refused(self):
        key = uuid.uuid4()
        first, again = self.submit(key=key), self.submit(key=key)
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["attempt_id"], again.json()["attempt_id"])
        self.assertEqual(self.submit({"s1": "Mombasa"}, key=key).status_code, 409)
        self.assertEqual(LearningQuizAttempt.objects.count(), 1)

    def test_typed_text_is_never_stored_or_echoed(self):
        secret = "mombasa-private-xyz"
        response = self.submit({"s1": secret})
        self.assertEqual(response.status_code, 201, response.content)
        attempt = LearningQuizAttempt.objects.get()
        self.assertNotIn(secret, str(attempt.feedback))
        self.assertNotIn(secret, attempt.request_fingerprint)
        self.assertNotIn(secret, str(response.json()))
        for event in LearningActivityEvent.objects.all():
            self.assertNotIn(secret, str(event.details))

    def test_exercises_feed_the_step_confirmation_rule(self):
        now = timezone.now()
        path = LearningPath.objects.create(
            scope="school", school=self.school, title="Path", language_code="en",
            access_tier="free", status="published", reviewed_by=self.publisher,
            reviewed_at=now, published_at=now)
        LearningPathItem.objects.create(path=path, position=1, item_type="resource",
                                        resource=self.resource, completion_rule="quiz_pass")
        LearningPathParticipation.objects.create(
            profile=self.profile, path=path, path_version=path.version, state="in_progress")
        self.submit(WRONG)
        self.assertEqual(LearningStepCompletion.objects.count(), 0)
        self.submit()
        self.assertEqual(LearningStepCompletion.objects.get().state, "awaiting_confirmation")


def text_q(**over):
    base = {"id": "s1", "type": "short_text", "prompt": "P", "accepted_answers": ["a"],
            "hint": "", "explanation": "E"}
    base.update(over)
    return base


def num_q(**over):
    base = {"id": "n1", "type": "numeric", "prompt": "P", "answer": "1", "tolerance": "0",
            "hint": "", "explanation": "E"}
    base.update(over)
    return base


def quiz(*questions):
    return {"schema_version": 1, "questions": list(questions)}


class ExerciseSchemaTests(APITestCase):
    def test_bad_exercises_are_rejected(self):
        no_hint = {k: v for k, v in text_q().items() if k != "hint"}
        cases = {
            "unknown type": text_q(type="essay"), "extra key": text_q(extra="x"),
            "no answers": text_q(accepted_answers=[]),
            "too many answers": text_q(accepted_answers=[str(i) for i in range(11)]),
            "repeated answer": text_q(accepted_answers=["Yes", "  yes "]),
            "answers not a list": text_q(accepted_answers="yes"),
            "blank prompt": text_q(prompt=""), "missing hint key": no_hint,
            "negative tolerance": num_q(tolerance="-1"), "nan answer": num_q(answer="nan"),
            "text answer": num_q(answer="abc"), "bool answer": num_q(answer=True),
            "bad id": text_q(id="bad id!"),
        }
        for name, question in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(QuizSchemaError):
                    normalize_practice_quiz(quiz(question))
        with self.assertRaises(QuizSchemaError):
            normalize_practice_quiz(quiz(text_q(), text_q()))

    def test_drafts_may_be_incomplete_and_normalising_is_stable(self):
        draft = quiz(text_q(prompt="", accepted_answers=[]), num_q(answer=""))
        self.assertEqual(len(normalize_practice_quiz(draft, allow_incomplete=True)["questions"]), 2)
        once = normalize_practice_quiz(EX_QUIZ)
        self.assertEqual(normalize_practice_quiz(once), once)
        self.assertNotIn("type", once["questions"][2])
