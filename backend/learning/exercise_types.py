"""Exercise types for practice quizzes: an extensible registry.

A question without a ``type`` key is the original multiple-choice question and
stays with quiz_schema and quiz_api unchanged. Every other question names a
type in TYPES. A type provides its author-side fields and validation and its
server-side answer check. Answer keys never leave the server and typed answers
are never stored: only the keyed fingerprint is kept.
To add a type (for example language practice), add one entry to TYPES.
"""
from decimal import Decimal, InvalidOperation

from .quiz_schema import QuizSchemaError, _ID, _plain_text

MAX_ACCEPTED_ANSWERS = 10
MAX_TYPED_ANSWER_CHARS = 200
MAX_NUMBER = Decimal("1000000000000")
REVEAL_FROM_SUBMISSION = 2


def normalize_text_answer(value):
    return " ".join(str(value).split()).casefold()


def _decimal(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(label)
    text = str(value).strip()
    if not text or len(text) > 40:
        raise ValueError(label)
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(label) from None
    if not number.is_finite() or abs(number) > MAX_NUMBER:
        raise ValueError(label)
    return number


def _plain(number):
    return format(number.normalize(), "f")


def _short_text_normalize(question, index, allow_incomplete):
    raw = question.get("accepted_answers")
    if (not isinstance(raw, list) or len(raw) > MAX_ACCEPTED_ANSWERS
            or (not raw and not allow_incomplete)):
        raise QuizSchemaError(
            f"Question {index} needs 1 to {MAX_ACCEPTED_ANSWERS} accepted answers.")
    cleaned, seen = [], set()
    for item in raw:
        text = _plain_text(item, f"Question {index} accepted answer",
                           MAX_TYPED_ANSWER_CHARS, allow_blank=False)
        key = normalize_text_answer(text)
        if key in seen:
            raise QuizSchemaError(f"Question {index} repeats an accepted answer.")
        seen.add(key)
        cleaned.append(text)
    return {"accepted_answers": cleaned}, bool(cleaned)


def _short_text_check(question, raw):
    if (not isinstance(raw, str) or not raw.strip()
            or len(raw) > MAX_TYPED_ANSWER_CHARS):
        return None, False, "Each text answer must be 1 to 200 characters."
    normalized = normalize_text_answer(raw)
    accepted = {normalize_text_answer(a) for a in question["accepted_answers"]}
    return normalized, normalized in accepted, None


def _numeric_normalize(question, index, allow_incomplete):
    raw = question.get("answer")
    if allow_incomplete and (raw is None or raw == ""):
        answer, complete = "", False
    else:
        try:
            answer, complete = _plain(_decimal(raw, "answer")), True
        except ValueError:
            raise QuizSchemaError(f"Question {index} needs a numeric answer.") from None
    try:
        tolerance = _decimal(question.get("tolerance"), "tolerance")
    except ValueError:
        raise QuizSchemaError(f"Question {index} needs a numeric tolerance.") from None
    if tolerance < 0:
        raise QuizSchemaError(f"Question {index} tolerance cannot be negative.")
    return {"answer": answer, "tolerance": _plain(tolerance)}, complete


def _numeric_check(question, raw):
    try:
        value = _decimal(raw, "answer")
    except ValueError:
        return None, False, "Each numeric answer must be a number."
    correct = abs(value - Decimal(question["answer"])) <= Decimal(question["tolerance"])
    return _plain(value), correct, None


TYPES = {
    "short_text": {
        "fields": {"id", "type", "prompt", "accepted_answers", "hint", "explanation"},
        "normalize": _short_text_normalize,
        "check": _short_text_check,
        "reveal": lambda question: question["accepted_answers"][0],
    },
    "numeric": {
        "fields": {"id", "type", "prompt", "answer", "tolerance", "hint", "explanation"},
        "normalize": _numeric_normalize,
        "check": _numeric_check,
        "reveal": lambda question: question["answer"],
    },
}


def normalize_exercise_question(question, index, allow_incomplete=False):
    spec = TYPES.get(question.get("type"))
    if spec is None:
        raise QuizSchemaError(f"Question {index} has an unsupported exercise type.")
    if set(question) != spec["fields"]:
        raise QuizSchemaError(f"Question {index} has unsupported or missing fields.")
    question_id = question.get("id")
    if not isinstance(question_id, str) or not _ID.fullmatch(question_id):
        raise QuizSchemaError(f"Question {index} needs a unique short id.")
    prompt = _plain_text(question.get("prompt"), f"Question {index} prompt", 500,
                         allow_blank=allow_incomplete)
    explanation = _plain_text(question.get("explanation"), f"Question {index} explanation",
                              600, allow_blank=allow_incomplete)
    hint = _plain_text(question.get("hint"), f"Question {index} hint", 300, allow_blank=True)
    fields, answers_complete = spec["normalize"](question, index, allow_incomplete)
    item = {"id": question_id, "type": question["type"], "prompt": prompt,
            "hint": hint, "explanation": explanation, **fields}
    return item, bool(prompt) and answers_complete


def learner_question(question):
    if "type" not in question:
        return {"id": question["id"], "prompt": question["prompt"],
                "options": question["options"]}
    # "options" stays an empty list so older cached screens do not break.
    return {"id": question["id"], "type": question["type"],
            "prompt": question["prompt"], "options": []}


def check_exercise_answer(question, raw, prior_attempts):
    """Return (normalized answer, correct, problem, extra feedback fields)."""
    spec = TYPES[question["type"]]
    normalized, correct, problem = spec["check"](question, raw)
    if problem:
        return None, False, problem, {}
    extra = {}
    if correct or prior_attempts + 1 >= REVEAL_FROM_SUBMISSION:
        extra["accepted_answer"] = spec["reveal"](question)
        extra["explanation"] = question["explanation"]
    elif question["hint"]:
        extra["hint"] = question["hint"]
    return normalized, correct, None, extra
