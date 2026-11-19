from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from learning.catalog_api import _age_for_profile
from learning.models import LearningProfile, LearningResource
from learning.question_lookup import approved_questions
from learning.test_question_bank import QUIZ
from schools.models import School, Student


class QuestionLookupTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Lookup School", code="LKUP")
        self.other = School.objects.create(name="Other Lookup", code="OLKP")
        self.publisher = User.objects.create_user("lk_pub", password="Test!123456")
        student = Student.objects.create(
            school=self.school, first_name="lk", last_name="Learner",
            admission_number="LK-1", date_of_birth=date(2010, 5, 5))
        user = User.objects.create_user("lk_learner", password="Test!123456")
        self.profile = LearningProfile.objects.create(
            user=user, account_kind="school_student", school=self.school,
            student=student, age_band="10_17", consent_state="verified", locale="en")

    def make(self, **kw):
        now = timezone.now()
        opts = dict(
            scope="school", school=self.school, title="Q", summary="s",
            body="Try these.", resource_type="interactive", practice_quiz=QUIZ,
            language_code="en", access_tier="free", status="published",
            reviewed_by=self.publisher, reviewed_at=now, published_at=now)
        opts.update(kw)
        return LearningResource.objects.create(**opts)

    def look(self):
        age = _age_for_profile(self.profile)
        return approved_questions(self.profile, age, ["en"], "en")

    def test_visible_resource_returns_questions_without_answers(self):
        self.make()
        rows = self.look()
        self.assertEqual(len(rows), 2)
        self.assertNotIn("correct_option_id", str(rows))
        self.assertNotIn("explanation", str(rows))

    def test_draft_returns_nothing(self):
        self.make(status="draft", published_at=None)
        self.assertEqual(self.look(), [])

    def test_other_school_returns_nothing(self):
        self.make(school=self.other)
        self.assertEqual(self.look(), [])

    def test_premium_for_free_learner_returns_nothing(self):
        self.make(access_tier="premium")
        self.assertEqual(self.look(), [])

    def test_archived_returns_nothing(self):
        self.make(status="archived")
        self.assertEqual(self.look(), [])

    def test_age_mismatch_returns_nothing(self):
        self.make(age_min=18)
        self.assertEqual(self.look(), [])

    def test_takedown_returns_nothing(self):
        now = timezone.now()
        self.make(status="archived", taken_down_at=now,
                  taken_down_by=self.publisher, retired_at=now)
        self.assertEqual(self.look(), [])
