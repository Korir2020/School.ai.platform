"""Server-verified, non-AI practice quizzes kept separate from academic records."""

import json
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .activity_api import _json_object, _learner_language, _locked_visible_resource, _visible_resource
from .catalog_api import _age_for_profile
from .models import LearningActivityEvent, LearningQuizAttempt
from .permissions import ActiveLearnerSelfService
from .quiz_schema import QuizSchemaError, learner_quiz, normalize_practice_quiz
from .throttles import LearningQuizThrottle

MAX_ATTEMPT_BODY_BYTES = 8192


def _resource_for_language(resource, language):
    # Quiz text is authored and reviewed in the resource's source language. An
    # approved prose translation does not silently imply an approved quiz/key.
    source_language = str(resource.language_code or "").lower().split("-")[0]
    return source_language == language


def _visible_quiz(request, resource_id, *, locked=False):
    profile = request.learning_profile
    language, candidates, error = _learner_language(request, profile)
    if error is not None:
        return None, None, error
    age = _age_for_profile(profile)
    if locked:
        resource = _locked_visible_resource(profile, resource_id, age, candidates)
    else:
        resource = _visible_resource(profile, resource_id, age, candidates)
    if resource is None or resource.resource_type != "interactive":
        return None, None, Response({"detail": "Learning quiz not found."}, status=404)
    if not _resource_for_language(resource, language):
        return None, None, Response({
            "code": "quiz_language_unavailable",
            "detail": "This practice quiz is not yet reviewed in your selected learning language.",
        }, status=409)
    try:
        quiz = normalize_practice_quiz(resource.practice_quiz)
    except QuizSchemaError:
        return None, None, Response({
            "code": "quiz_not_ready",
            "detail": "This interactive resource does not have a complete reviewed practice quiz.",
        }, status=409)
    return resource, quiz, None


def _attempt_response(attempt, *, status=200):
    return Response({
        "attempt_id": attempt.pk,
        "resource_id": attempt.resource_id,
        "resource_version": attempt.resource_version,
        "completed_at": attempt.completed_at,
        "question_count": attempt.question_count,
        "correct_count": attempt.correct_count,
        "feedback": attempt.feedback,
        "recording_policy": "A valid practice attempt is recorded privately; it is not a Marian exam mark, report-card result, or mastery certification.",
    }, status=status)


def _validated_answers(data, quiz):
    if set(data) != {"idempotency_key", "resource_version", "answers"}:
        return None, None, "Only idempotency_key, resource_version, and answers are accepted."
    try:
        key = uuid.UUID(str(data["idempotency_key"]))
    except (TypeError, ValueError, AttributeError):
        return None, None, "A UUID idempotency_key is required."
    version = data.get("resource_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return None, None, "resource_version must be a positive integer."
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return None, None, "answers must map every question id to one option id."
    question_by_id = {question["id"]: question for question in quiz["questions"]}
    if set(answers) != set(question_by_id):
        return None, None, "Answer every question exactly once using the current quiz question ids."
    feedback = []
    correct_count = 0
    normalized_answers = {}
    for question in quiz["questions"]:
        selected = answers.get(question["id"])
        option_ids = {option["id"] for option in question["options"]}
        if not isinstance(selected, str) or selected not in option_ids:
            return None, None, "Each answer must identify an option in its question."
        normalized_answers[question["id"]] = selected
        correct = selected == question["correct_option_id"]
        correct_count += int(correct)
        feedback.append({
            "question_id": question["id"],
            "correct": correct,
            "correct_option_id": question["correct_option_id"],
            "explanation": question["explanation"],
        })
    canonical = json.dumps(normalized_answers, sort_keys=True, separators=(",", ":"))
    fingerprint = salted_hmac(
        "marian.learning.quiz-attempt.v1", canonical,
        secret=settings.SECRET_KEY, algorithm="sha256",
    ).hexdigest()
    return {"key": key, "version": version, "answers": normalized_answers}, {
        "correct_count": correct_count,
        "question_count": len(quiz["questions"]),
        "feedback": feedback,
        "request_fingerprint": fingerprint,
    }, None


@api_view(["GET"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
@throttle_classes([LearningQuizThrottle])
def learner_practice_quiz(request, resource_id):
    if set(request.query_params) - {"lang"}:
        return Response({"detail": "Unsupported quiz filter."}, status=400)
    resource, quiz, error = _visible_quiz(request, resource_id)
    if error is not None:
        return error
    return Response({
        "resource_id": resource.pk,
        "resource_version": resource.version,
        "language_code": resource.language_code,
        "quiz": learner_quiz(quiz),
    })


@api_view(["POST"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
@throttle_classes([LearningQuizThrottle])
def submit_practice_quiz(request, resource_id):
    data, error = _json_object(request, max_bytes=MAX_ATTEMPT_BODY_BYTES)
    if error is not None:
        return error

    profile = request.learning_profile
    with transaction.atomic():
        resource, quiz, error = _visible_quiz(request, resource_id, locked=True)
        if error is not None:
            return error
        validated, outcome, validation_error = _validated_answers(data, quiz)
        if validation_error:
            return Response({"detail": validation_error}, status=400)
        if validated["version"] != resource.version:
            return Response({
                "code": "stale_quiz_version",
                "detail": "The quiz changed after it was opened. Reload the current version before submitting.",
            }, status=409)

        existing = LearningQuizAttempt.objects.select_for_update().filter(
            profile=profile, idempotency_key=validated["key"],
        ).first()
        if existing is not None:
            if (
                existing.resource_id != resource.pk
                or existing.resource_version != resource.version
                or existing.request_fingerprint != outcome["request_fingerprint"]
            ):
                return Response({"detail": "This idempotency key was already used for a different quiz submission."}, status=409)
            return _attempt_response(existing, status=200)

        now = timezone.now()
        try:
            with transaction.atomic():
                attempt = LearningQuizAttempt.objects.create(
                    profile=profile,
                    resource=resource,
                    resource_version=resource.version,
                    idempotency_key=validated["key"],
                    request_fingerprint=outcome["request_fingerprint"],
                    question_count=outcome["question_count"],
                    correct_count=outcome["correct_count"],
                    feedback=outcome["feedback"],
                    completed_at=now,
                )
        except IntegrityError:
            existing = LearningQuizAttempt.objects.filter(
                profile=profile, idempotency_key=validated["key"],
            ).first()
            if existing is None:
                raise
            if (
                existing.resource_id != resource.pk
                or existing.resource_version != resource.version
                or existing.request_fingerprint != outcome["request_fingerprint"]
            ):
                return Response({"detail": "This idempotency key was already used for a different quiz submission."}, status=409)
            return _attempt_response(existing, status=200)

        # Completion is derived only after server-side option validation. The
        # event deliberately omits answers, correctness, score, and free text.
        event_key = uuid.uuid5(uuid.NAMESPACE_URL, f"marian-learning-quiz-attempt:{attempt.pk}")
        LearningActivityEvent.objects.get_or_create(
            profile=profile,
            idempotency_key=event_key,
            defaults={
                "event_type": "completed",
                "resource": resource,
                "details": {"evidence_type": "validated_practice_quiz", "resource_version": resource.version},
                "occurred_at": now,
            },
        )
    try:
        from .step_completion import record_quiz_evidence
        record_quiz_evidence(profile, resource, attempt)
    except Exception:  # evidence must never lose a stored attempt
        import logging
        logging.getLogger(__name__).exception("step completion evidence failed")
    return _attempt_response(attempt, status=201)
