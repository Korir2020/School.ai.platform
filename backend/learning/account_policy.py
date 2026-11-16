"""Shared age-policy helpers for learning-account lifecycle operations.

Exact dates of birth are consumed only by trusted server-side code. APIs should
return an age band, never a learner's date of birth or exact age.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

MINIMUM_APPROVED_INDEPENDENT_AGE = 10
ADULT_AGE = 18
MAX_PLAUSIBLE_AGE = 120


def minimum_independent_age():
    """Return the configured minimum, constrained to the approved 10–17 range."""
    value = getattr(settings, "LEARNING_MIN_INDEPENDENT_AGE", MINIMUM_APPROVED_INDEPENDENT_AGE)
    try:
        age = int(value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("LEARNING_MIN_INDEPENDENT_AGE must be an integer from 10 to 17.") from exc
    if not MINIMUM_APPROVED_INDEPENDENT_AGE <= age < ADULT_AGE:
        raise ImproperlyConfigured("LEARNING_MIN_INDEPENDENT_AGE must be from 10 to 17.")
    return age


def age_on(date_of_birth, today=None):
    """Return an age in whole years, or None for missing/future/implausible DOB."""
    if not isinstance(date_of_birth, date):
        return None
    today = today or date.today()
    age = today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )
    if age < 0 or age > MAX_PLAUSIBLE_AGE:
        return None
    return age


def age_band_for(date_of_birth, today=None):
    """Return (band, exact_age); exact age remains internal and is never serialized."""
    age = age_on(date_of_birth, today=today)
    if age is None:
        return "unknown", None
    if age < MINIMUM_APPROVED_INDEPENDENT_AGE:
        return "under_10", age
    if age < ADULT_AGE:
        return "10_17", age
    return "adult", age


def independent_registration_policy(date_of_birth, today=None):
    """Return a minimal policy result; provider verification is evaluated separately."""
    band, age = age_band_for(date_of_birth, today=today)
    minimum = minimum_independent_age()
    if age is None:
        return {"allowed_by_age": False, "age_band": "unknown", "guardian_required": True}
    if age < minimum:
        return {"allowed_by_age": False, "age_band": band, "guardian_required": True}
    if age < ADULT_AGE:
        return {"allowed_by_age": True, "age_band": band, "guardian_required": True}
    return {"allowed_by_age": True, "age_band": band, "guardian_required": False}
