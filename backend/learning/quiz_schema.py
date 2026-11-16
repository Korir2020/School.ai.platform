"""Schema validation for the first non-AI interactive learning activity.

Quiz text is plain text, authored in the resource's source language, and reviewed
through the existing school content workflow. Answer keys are never part of the
learner catalogue response.
"""

import json
import re
from html import unescape

from django.utils.html import strip_tags


MAX_QUIZ_QUESTIONS = 20
MAX_QUIZ_OPTIONS = 6
MAX_QUIZ_BYTES = 32768
_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class QuizSchemaError(ValueError):
    """The submitted quiz does not match the bounded practice-quiz schema."""


def _plain_text(value, label, maximum, *, allow_blank):
    if not isinstance(value, str):
        raise QuizSchemaError(f"{label} must be text.")
    cleaned = unescape(strip_tags(value)).strip()
    if len(cleaned) > maximum:
        raise QuizSchemaError(f"{label} exceeds {maximum} characters.")
    if not allow_blank and not cleaned:
        raise QuizSchemaError(f"{label} is required.")
    return cleaned


def normalize_practice_quiz(value, *, allow_incomplete=False):
    """Validate and normalize a quiz JSON object.

    Incomplete draft mode is for the private authoring form only. Submission for
    review, learner delivery, and answer checking must use the complete schema.
    """
    if value == {} and allow_incomplete:
        return {"schema_version": 1, "questions": []}
    if not isinstance(value, dict) or set(value) != {"schema_version", "questions"}:
        raise QuizSchemaError("practice_quiz must contain only schema_version and questions.")
    if value.get("schema_version") != 1:
        raise QuizSchemaError("Unsupported practice_quiz schema_version.")
    questions = value.get("questions")
    if not isinstance(questions, list) or len(questions) > MAX_QUIZ_QUESTIONS:
        raise QuizSchemaError(f"A practice quiz must contain at most {MAX_QUIZ_QUESTIONS} questions.")
    if not allow_incomplete and not questions:
        raise QuizSchemaError("Add at least one complete question before submitting this interactive resource.")

    normalized = []
    seen_question_ids = set()
    complete_count = 0
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict) or set(question) != {
            "id", "prompt", "options", "correct_option_id", "explanation",
        }:
            raise QuizSchemaError(f"Question {index} has unsupported or missing fields.")
        question_id = question.get("id")
        if not isinstance(question_id, str) or not _ID.fullmatch(question_id) or question_id in seen_question_ids:
            raise QuizSchemaError(f"Question {index} needs a unique short id.")
        seen_question_ids.add(question_id)
        prompt = _plain_text(question.get("prompt"), f"Question {index} prompt", 500, allow_blank=allow_incomplete)
        explanation = _plain_text(question.get("explanation"), f"Question {index} explanation", 600, allow_blank=True)
        options = question.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= MAX_QUIZ_OPTIONS:
            raise QuizSchemaError(f"Question {index} must have between 2 and {MAX_QUIZ_OPTIONS} options.")
        normalized_options = []
        option_ids = set()
        for option_index, option in enumerate(options, start=1):
            if not isinstance(option, dict) or set(option) != {"id", "text"}:
                raise QuizSchemaError(f"Question {index}, option {option_index} has unsupported or missing fields.")
            option_id = option.get("id")
            if not isinstance(option_id, str) or not _ID.fullmatch(option_id) or option_id in option_ids:
                raise QuizSchemaError(f"Question {index} needs unique short option ids.")
            option_ids.add(option_id)
            option_text = _plain_text(option.get("text"), f"Question {index}, option {option_index}", 240, allow_blank=allow_incomplete)
            normalized_options.append({"id": option_id, "text": option_text})
        correct_id = question.get("correct_option_id")
        if not isinstance(correct_id, str) or correct_id not in option_ids:
            raise QuizSchemaError(f"Question {index} must identify one of its option ids as correct.")
        complete = bool(prompt) and all(option["text"] for option in normalized_options)
        if complete:
            complete_count += 1
        elif not allow_incomplete:
            raise QuizSchemaError(f"Question {index} and all of its options must contain text.")
        normalized.append({
            "id": question_id,
            "prompt": prompt,
            "options": normalized_options,
            "correct_option_id": correct_id,
            "explanation": explanation,
        })

    if not allow_incomplete and complete_count != len(questions):
        raise QuizSchemaError("Every quiz question must be complete before submission.")
    result = {"schema_version": 1, "questions": normalized}
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_QUIZ_BYTES:
        raise QuizSchemaError(f"practice_quiz exceeds the {MAX_QUIZ_BYTES}-byte limit.")
    return result


def learner_quiz(quiz):
    """Return only prompts and choices; omit every answer key and explanation."""
    normalized = normalize_practice_quiz(quiz)
    return {
        "schema_version": normalized["schema_version"],
        "questions": [
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "options": question["options"],
            }
            for question in normalized["questions"]
        ],
    }
