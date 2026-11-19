from django.db import transaction

LIMITS = {"prompt": 500, "correct_option_id": 40, "explanation": 600}


def sync_resource_questions(resource):
    from .models import LearningQuestion
    quiz = resource.practice_quiz if isinstance(resource.practice_quiz, dict) else {}
    items = quiz.get("questions") if isinstance(quiz.get("questions"), list) else []
    wanted = {}
    for i, q in enumerate(items):
        if isinstance(q, dict) and isinstance(q.get("id"), str) and q["id"]:
            opts = q.get("options")
            wanted[q["id"]] = {"position": i, "options": opts if isinstance(opts, list) else [],
                               **{k: str(q.get(k) or "")[:n] for k, n in LIMITS.items()}}
    with transaction.atomic():
        qs = LearningQuestion.objects.filter(resource=resource)
        rows = {r.question_key: r for r in qs}
        qs.exclude(question_key__in=list(wanted)).delete()
        for key, data in wanted.items():
            row = rows.get(key)
            if row is None:
                row = LearningQuestion.objects.create(
                    resource=resource, question_key=key, difficulty=resource.difficulty,
                    language_code=resource.language_code, **data)
                row.topics.set(resource.topics.all())
            elif any(getattr(row, f) != v for f, v in data.items()):
                for f, v in data.items():
                    setattr(row, f, v)
                row.save()
