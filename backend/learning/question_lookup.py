"""Read-only lookup of bank questions a learner may see."""
from .catalog_api import _resource_is_visible, _resource_queryset
from .models import LearningQuestion
from .quiz_api import _resource_for_language


def approved_questions(profile, age, candidates, language,
                       topic_id=None, difficulty=None):
    rows = LearningQuestion.objects.filter(resource__resource_type="interactive")
    if topic_id is not None:
        rows = rows.filter(topics=topic_id)
    if difficulty:
        rows = rows.filter(difficulty=difficulty)
    ids = set(rows.values_list("resource_id", flat=True))
    if not ids:
        return []
    visible = {
        r.pk
        for r in _resource_queryset(profile, age, candidates).filter(pk__in=ids)
        if _resource_is_visible(profile, r, age, candidates)
        and _resource_for_language(r, language)
    }
    rows = rows.filter(resource_id__in=visible)
    return [
        {"id": q.id, "resource_id": q.resource_id, "question_key": q.question_key,
         "prompt": q.prompt, "options": q.options, "difficulty": q.difficulty,
         "language_code": q.language_code}
        for q in rows.order_by("resource_id", "position", "id")
    ]
