from django.db import migrations


def copy_quizzes(apps, schema_editor):
    Resource = apps.get_model("learning", "LearningResource")
    Question = apps.get_model("learning", "LearningQuestion")
    for res in Resource.objects.all().iterator(chunk_size=200):
        quiz = res.practice_quiz if isinstance(res.practice_quiz, dict) else {}
        items = quiz.get("questions") if isinstance(quiz.get("questions"), list) else []
        topics = None
        for i, q in enumerate(items):
            if not (isinstance(q, dict) and isinstance(q.get("id"), str) and q["id"]):
                continue
            opts = q.get("options")
            row, created = Question.objects.get_or_create(
                resource=res, question_key=q["id"],
                defaults={"position": i, "options": opts if isinstance(opts, list) else [],
                          "prompt": str(q.get("prompt") or "")[:500],
                          "correct_option_id": str(q.get("correct_option_id") or "")[:40],
                          "explanation": str(q.get("explanation") or "")[:600],
                          "difficulty": res.difficulty, "language_code": res.language_code})
            if created:
                topics = list(res.topics.all()) if topics is None else topics
                row.topics.set(topics)


class Migration(migrations.Migration):
    dependencies = [("learning", "0017_learning_question")]
    operations = [migrations.RunPython(copy_quizzes, migrations.RunPython.noop)]
