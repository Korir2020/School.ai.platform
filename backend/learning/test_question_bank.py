import importlib

from django.apps import apps as live_apps
from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase

from .models import LearningQuestion, LearningResource

QUIZ = {"schema_version": 1, "questions": [
    {"id": "q1", "prompt": "2 + 2?", "options": [{"id": "a", "text": "3"}, {"id": "b", "text": "4"}],
     "correct_option_id": "b", "explanation": "Add."},
    {"id": "q2", "prompt": "Capital of Kenya?", "options": [{"id": "a", "text": "Nairobi"}, {"id": "b", "text": "Mombasa"}],
     "correct_option_id": "a", "explanation": "It is Nairobi."},
]}


def make_resource(**extra):
    User = get_user_model()
    kw = {"title": "Bank test", "scope": "public", "origin": "marian", "resource_type": "interactive"}
    kw.update(extra)
    for f in LearningResource._meta.concrete_fields:
        if f.primary_key or f.name in kw or f.null or f.has_default() or getattr(f, "auto_now_add", False) or getattr(f, "auto_now", False):
            continue
        if isinstance(f, models.ForeignKey) and f.related_model is User:
            kw[f.name] = User.objects.create_user(username="bank_" + f.name, password="pw-12345-x")
        elif not isinstance(f, (models.CharField, models.TextField)):
            raise AssertionError("test helper needs a value for field " + f.name)
    return LearningResource.objects.create(**kw)


class QuestionBankTests(TestCase):
    def rows(self, res):
        return list(LearningQuestion.objects.filter(resource=res))

    def test_new_resource_with_quiz_fills_the_bank(self):
        res = make_resource(practice_quiz=QUIZ)
        rows = self.rows(res)
        self.assertEqual([r.question_key for r in rows], ["q1", "q2"])
        self.assertEqual([r.position for r in rows], [0, 1])
        self.assertEqual(rows[0].correct_option_id, "b")

    def test_resource_without_quiz_has_no_rows(self):
        self.assertEqual(self.rows(make_resource()), [])

    def test_editing_the_quiz_updates_adds_and_removes_rows(self):
        res = make_resource(practice_quiz=QUIZ)
        first_id = LearningQuestion.objects.get(resource=res, question_key="q1").id
        new_q = {"id": "q3", "prompt": "3 + 3?", "options": [{"id": "a", "text": "6"}, {"id": "b", "text": "7"}],
                 "correct_option_id": "a", "explanation": "Six."}
        res.practice_quiz = {"schema_version": 1, "questions": [dict(QUIZ["questions"][0], prompt="2 plus 2?"), new_q]}
        res.save()
        rows = self.rows(res)
        self.assertEqual([r.question_key for r in rows], ["q1", "q3"])
        self.assertEqual(rows[0].id, first_id)
        self.assertEqual(rows[0].prompt, "2 plus 2?")

    def test_deleting_the_resource_deletes_its_rows(self):
        res = make_resource(practice_quiz=QUIZ)
        res.delete()
        self.assertEqual(LearningQuestion.objects.count(), 0)

    def test_copy_migration_is_complete_and_repeatable(self):
        res = make_resource(practice_quiz=QUIZ)
        LearningQuestion.objects.filter(resource=res).delete()
        mod = importlib.import_module("learning.migrations.0018_copy_quizzes_to_bank")
        mod.copy_quizzes(live_apps, None)
        mod.copy_quizzes(live_apps, None)
        self.assertEqual(len(self.rows(res)), 2)
