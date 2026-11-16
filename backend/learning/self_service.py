"""Self-service profile/preferences API for public adults and active students.

This endpoint changes only the caller's own learning locale and preferences. It
never accepts or returns user, school, student, age, or consent identifiers as
writeable values, and it does not read academic records or learning content.
"""

import re

from django.db import transaction
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .models import LearningPreference, LearningResource, LearningTopic
from .permissions import ActiveLearnerSelfService
from .throttles import LearningProfileThrottle


SUPPORTED_LOCALES = {"en", "sw", "en-KE", "sw-KE"}
LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
PROFILE_FIELDS = {"locale", "preferences"}
PREFERENCE_FIELDS = {
    "topic_ids",
    "preferred_languages",
    "preferred_formats",
    "preferred_difficulty",
    "recommendations_enabled",
}
RESOURCE_FORMATS = {value for value, _label in LearningResource.RESOURCE_TYPES}
DIFFICULTIES = {value for value, _label in LearningResource.DIFFICULTIES}
MAX_TOPICS = 50
MAX_LIST_ITEMS = 10


def _normalize_locale(value):
    if not isinstance(value, str):
        return None
    parts = value.strip().split("-")
    if not parts[0] or len(parts) > 2:
        return None
    normalized = parts[0].lower()
    if len(parts) == 2:
        normalized += "-" + parts[1].upper()
    return normalized if normalized in SUPPORTED_LOCALES else None


def _normalize_language_codes(value):
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        return None
    normalized = []
    for item in value:
        if not isinstance(item, str):
            return None
        code = item.strip()
        parts = code.split("-")
        code = parts[0].lower() + "".join("-" + part.upper() for part in parts[1:])
        if not LANGUAGE_CODE_RE.fullmatch(code):
            return None
        normalized.append(code)
    if len(set(normalized)) != len(normalized):
        return None
    return normalized


def _normalize_choice_list(value, allowed, limit=MAX_LIST_ITEMS):
    if not isinstance(value, list) or len(value) > limit:
        return None
    normalized = []
    for item in value:
        if not isinstance(item, str):
            return None
        choice = item.strip().lower()
        if choice not in allowed:
            return None
        normalized.append(choice)
    return normalized if len(set(normalized)) == len(normalized) else None


def _serialize(profile):
    try:
        preferences = profile.preferences
    except LearningPreference.DoesNotExist:
        preferences = None
    if preferences is None:
        topic_ids = []
        languages = []
        formats = []
        difficulty = ""
        recommendations_enabled = True
    else:
        topic_ids = list(
            preferences.topics.filter(is_active=True)
            .order_by("name", "pk")
            .values_list("pk", flat=True)
        )
        languages = preferences.preferred_languages
        formats = preferences.preferred_formats
        difficulty = preferences.preferred_difficulty
        recommendations_enabled = preferences.recommendations_enabled
    return {
        "profile": {
            "account_kind": profile.account_kind,
            "locale": profile.locale,
            "age_band": profile.age_band,
            "consent_state": profile.consent_state,
        },
        "preferences": {
            "topic_ids": topic_ids,
            "preferred_languages": languages,
            "preferred_formats": formats,
            "preferred_difficulty": difficulty,
            "recommendations_enabled": recommendations_enabled,
        },
    }


def _validate_payload(data):
    errors = {}
    updates = {}
    if not hasattr(data, "keys"):
        return None, {"detail": "Send a JSON object."}

    unknown = set(data.keys()) - PROFILE_FIELDS
    if unknown:
        for key in unknown:
            errors[key] = "This field is read-only or unsupported."

    if "locale" in data:
        locale = _normalize_locale(data.get("locale"))
        if locale is None:
            errors["locale"] = "Choose one of the supported interface locales: en, sw, en-KE, or sw-KE."
        else:
            updates["locale"] = locale

    if "preferences" in data:
        preference_data = data.get("preferences")
        if not isinstance(preference_data, dict):
            errors["preferences"] = "Send preferences as an object."
        else:
            unknown_preferences = set(preference_data.keys()) - PREFERENCE_FIELDS
            for key in unknown_preferences:
                errors[f"preferences.{key}"] = "This field is unsupported."
            preference_updates = {}
            if "topic_ids" in preference_data:
                ids = preference_data.get("topic_ids")
                if (
                    not isinstance(ids, list)
                    or len(ids) > MAX_TOPICS
                    or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in ids)
                    or len(set(ids)) != len(ids)
                ):
                    errors["preferences.topic_ids"] = f"Provide at most {MAX_TOPICS} distinct positive topic IDs."
                else:
                    active_ids = set(
                        LearningTopic.objects.filter(pk__in=ids, is_active=True)
                        .values_list("pk", flat=True)
                    )
                    if active_ids != set(ids):
                        errors["preferences.topic_ids"] = "One or more topic selections are unavailable."
                    else:
                        preference_updates["topic_ids"] = ids
            if "preferred_languages" in preference_data:
                languages = _normalize_language_codes(preference_data.get("preferred_languages"))
                if languages is None:
                    errors["preferences.preferred_languages"] = "Use up to 10 distinct language codes, such as en or sw."
                else:
                    preference_updates["preferred_languages"] = languages
            if "preferred_formats" in preference_data:
                formats = _normalize_choice_list(
                    preference_data.get("preferred_formats"), RESOURCE_FORMATS,
                )
                if formats is None:
                    errors["preferences.preferred_formats"] = "Choose up to 10 distinct supported learning formats."
                else:
                    preference_updates["preferred_formats"] = formats
            if "preferred_difficulty" in preference_data:
                difficulty = preference_data.get("preferred_difficulty")
                if not isinstance(difficulty, str) or difficulty.strip().lower() not in DIFFICULTIES | {""}:
                    errors["preferences.preferred_difficulty"] = "Choose beginner, intermediate, advanced, or an empty value."
                else:
                    preference_updates["preferred_difficulty"] = difficulty.strip().lower()
            if "recommendations_enabled" in preference_data:
                enabled = preference_data.get("recommendations_enabled")
                if not isinstance(enabled, bool):
                    errors["preferences.recommendations_enabled"] = "Enter true or false."
                else:
                    preference_updates["recommendations_enabled"] = enabled
            updates["preferences"] = preference_updates

    if not errors and (
        not updates or (set(updates) == {"preferences"} and not updates["preferences"])
    ):
        errors["detail"] = "Nothing to update."
    return updates, errors


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningProfileThrottle])
def learner_me(request):
    profile = request.learning_profile
    if request.method == "GET":
        return Response(_serialize(profile))

    updates, errors = _validate_payload(request.data)
    if errors:
        return Response({"errors": errors}, status=400)

    with transaction.atomic():
        # Re-bind ownership inside the write transaction; never trust a client ID.
        from .models import LearningProfile

        profile = LearningProfile.objects.select_for_update().get(
            pk=profile.pk, user=request.user,
        )
        if "locale" in updates:
            profile.locale = updates["locale"]
            profile.save(update_fields=["locale", "updated_at"])

        preference_updates = updates.get("preferences", {})
        if preference_updates:
            preference, _created = LearningPreference.objects.get_or_create(profile=profile)
            scalar_fields = []
            for field in (
                "preferred_languages",
                "preferred_formats",
                "preferred_difficulty",
                "recommendations_enabled",
            ):
                if field in preference_updates:
                    setattr(preference, field, preference_updates[field])
                    scalar_fields.append(field)
            if scalar_fields:
                preference.save(update_fields=[*scalar_fields, "updated_at"])
            if "topic_ids" in preference_updates:
                preference.topics.set(
                    LearningTopic.objects.filter(
                        pk__in=preference_updates["topic_ids"], is_active=True,
                    )
                )

    profile.refresh_from_db()
    return Response(_serialize(profile))
