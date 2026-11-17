"""Quiz-pass evidence for learning-path steps.

A passing quiz attempt is evidence only and never completes a step by itself.
It moves the step to awaiting_confirmation and an authorised teacher confirms
or rejects it. Independent (public) learners have no teacher, so a repeat pass
on a later day at a higher bar verifies the step instead. Nothing here reads
or changes examination, report, attendance, fee or risk data.
"""
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    LearningPathItem,
    LearningPathParticipation,
    LearningStepCompletion,
)

DEFAULT_PASS_PERCENT = 70
REPEAT_BONUS_POINTS = 10
_RULE = re.compile(r"^quiz_pass(?::([1-9][0-9]?|100))?$")


def is_quiz_pass_rule(rule):
    return isinstance(rule, str) and _RULE.match(rule) is not None


def pass_percent_for(rule):
    match = _RULE.match(rule) if isinstance(rule, str) else None
    if match is None:
        return None
    return int(match.group(1)) if match.group(1) else DEFAULT_PASS_PERCENT


def score_percent(attempt):
    if not attempt.question_count:
        return 0
    return (attempt.correct_count * 100) // attempt.question_count


def independent_verification_enabled():
    return bool(getattr(settings, "LEARNING_INDEPENDENT_REPEAT_VERIFICATION", True))


def record_quiz_evidence(profile, resource, attempt):
    """Update step confirmation rows from one stored quiz attempt."""
    percent = score_percent(attempt)
    independent = (
        profile.account_kind == "public_learner"
        and independent_verification_enabled()
    )
    method = "repeat_practice" if independent else "teacher"
    now = timezone.now()
    touched = 0
    participations = LearningPathParticipation.objects.filter(
        profile=profile, state="in_progress"
    ).select_related("path")
    for participation in participations:
        path = participation.path
        if participation.path_version != path.version:
            continue
        items = LearningPathItem.objects.filter(
            path_id=path.pk,
            resource_id=resource.pk,
            completion_rule__startswith="quiz_pass",
        )
        for item in items:
            needed = pass_percent_for(item.completion_rule)
            if needed is None or percent < needed:
                continue
            with transaction.atomic():
                row, created = (
                    LearningStepCompletion.objects.select_for_update().get_or_create(
                        profile=profile,
                        path=path,
                        path_version=path.version,
                        item_position=item.position,
                        defaults={
                            "resource": resource,
                            "attempt": attempt,
                            "state": "awaiting_confirmation",
                            "method": method,
                        },
                    )
                )
                if created:
                    touched += 1
                elif row.state == "rejected":
                    row.state = "awaiting_confirmation"
                    row.method = method
                    row.attempt = attempt
                    row.decided_by = None
                    row.decided_at = None
                    row.save(update_fields=[
                        "state", "method", "attempt", "decided_by",
                        "decided_at", "updated_at",
                    ])
                    touched += 1
                elif (
                    independent
                    and row.state == "awaiting_confirmation"
                    and row.method == "repeat_practice"
                    and timezone.localdate(row.created_at) < timezone.localdate(now)
                    and percent >= min(100, needed + REPEAT_BONUS_POINTS)
                ):
                    row.state = "confirmed"
                    row.decided_at = now
                    row.save(update_fields=["state", "decided_at", "updated_at"])
                    touched += 1
    return touched
