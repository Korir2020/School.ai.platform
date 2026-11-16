"""Self-service learning goal APIs, strictly scoped to the caller's profile."""

import re
from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .catalog_api import (
    _age_for_profile,
    _language_candidates,
    _normalize_language,
    _path_is_visible as _catalog_path_is_visible,
    _path_queryset,
    _topic_queryset,
)
from .models import LearningGoal, LearningPath, LearningPreference, LearningProfile, LearningTopic
from .permissions import ActiveLearnerSelfService
from .throttles import LearningProfileThrottle


COLLECTION_FIELDS = {"title", "description", "topic_id", "path_id", "target_date"}
DETAIL_FIELDS = COLLECTION_FIELDS | {"state"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_DESCRIPTION = 5000
MAX_LIST_RESULTS = 200
TERMINAL_STATES = {"completed", "closed"}


def _goal_language(profile):
    try:
        preferred = profile.preferences.preferred_languages
    except LearningPreference.DoesNotExist:
        preferred = []
    if isinstance(preferred, list):
        for value in preferred:
            language = _normalize_language(value)
            if language:
                return language
    return _normalize_language(profile.locale) or "en"


def _visible_path(profile, raw_id, lock=False, age=None, candidates=None):
    if not isinstance(raw_id, int) or isinstance(raw_id, bool) or raw_id <= 0:
        return None
    if lock:
        locked_path = LearningPath.objects.select_for_update().filter(pk=raw_id).first()
        if locked_path is None:
            return None
    age = _age_for_profile(profile) if age is None else age
    candidates = candidates or _language_candidates(_goal_language(profile))
    path = _path_queryset(profile, age, candidates).filter(pk=raw_id).first()
    return path if path is not None and _catalog_path_is_visible(profile, path, age, candidates) else None


def _visible_topic(profile, raw_id, lock=False, age=None):
    if not isinstance(raw_id, int) or isinstance(raw_id, bool) or raw_id <= 0:
        return None
    if lock:
        if not LearningTopic.objects.select_for_update().filter(pk=raw_id).exists():
            return None
    age = _age_for_profile(profile) if age is None else age
    return _topic_queryset(profile, age).filter(pk=raw_id).first()


def _goal_link_maps(profile, goals, age, candidates):
    topic_ids = {goal.topic_id for goal in goals if goal.topic_id}
    path_ids = {goal.path_id for goal in goals if goal.path_id}
    topics = {}
    paths = {}
    if topic_ids:
        topics = {
            topic.pk: topic
            for topic in _topic_queryset(profile, age).filter(pk__in=topic_ids)
        }
    if path_ids:
        paths = {
            path.pk: path
            for path in _path_queryset(profile, age, candidates).filter(pk__in=path_ids)
            if _catalog_path_is_visible(profile, path, age, candidates)
        }
    return topics, paths


def _goal_json(goal, profile, visible_topics=None, visible_paths=None):
    if visible_topics is None or visible_paths is None:
        age = _age_for_profile(profile)
        candidates = _language_candidates(_goal_language(profile))
        visible_topics, visible_paths = _goal_link_maps(profile, [goal], age, candidates)
    topic = visible_topics.get(goal.topic_id)
    path = visible_paths.get(goal.path_id)
    return {
        "id": goal.pk,
        "title": goal.title,
        "description": goal.description,
        "topic": ({"id": topic.pk, "code": topic.code, "name": topic.name} if topic else None),
        "path": ({"id": path.pk, "title": path.title} if path else None),
        "target_date": goal.target_date,
        "state": goal.state,
        "created_at": goal.created_at,
        "updated_at": goal.updated_at,
        "closed_at": goal.closed_at,
    }


def _date_value(value):
    if value is None:
        return None, None
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return None, "Use a date in YYYY-MM-DD format or null."
    try:
        return date.fromisoformat(value), None
    except ValueError:
        return None, "Use a valid calendar date."


def _validate_goal_data(data, profile, instance=None, lock=False, age=None, candidates=None):
    errors = {}
    if not hasattr(data, "keys"):
        return None, {"detail": "Send a JSON object."}
    allowed = DETAIL_FIELDS if instance is not None else COLLECTION_FIELDS
    for key in set(data.keys()) - allowed:
        errors[key] = "This field is read-only or unsupported."

    attrs = {}
    if instance is None and "title" not in data:
        errors["title"] = "This field is required."
    if "title" in data:
        value = data.get("title")
        if not isinstance(value, str) or not value.strip():
            errors["title"] = "Enter a non-empty title."
        elif len(value.strip()) > 200:
            errors["title"] = "Use at most 200 characters."
        else:
            attrs["title"] = value.strip()

    if "description" in data:
        value = data.get("description")
        if not isinstance(value, str):
            errors["description"] = "Enter text."
        elif len(value) > MAX_DESCRIPTION:
            errors["description"] = f"Use at most {MAX_DESCRIPTION} characters."
        else:
            attrs["description"] = value.strip()

    age = _age_for_profile(profile) if age is None else age
    candidates = candidates or _language_candidates(_goal_language(profile))
    for field in ("topic_id", "path_id"):
        if field not in data:
            continue
        raw_id = data.get(field)
        if raw_id is None:
            attrs[field[:-3]] = None
            continue
        if field == "path_id":
            obj = _visible_path(profile, raw_id, lock=lock, age=age, candidates=candidates)
        else:
            obj = _visible_topic(profile, raw_id, lock=lock, age=age)
        if obj is None:
            errors[field] = "Select an active topic or published learning path available to this account, or null."
        else:
            attrs[field[:-3]] = obj

    if "target_date" in data:
        value, error = _date_value(data.get("target_date"))
        if error:
            errors["target_date"] = error
        else:
            attrs["target_date"] = value

    if "state" in data:
        state = data.get("state")
        valid_states = {value for value, _label in LearningGoal.STATES}
        if not isinstance(state, str) or state not in valid_states:
            errors["state"] = "Choose active, completed, paused, or closed."
        else:
            attrs["state"] = state

    if instance is not None and not data:
        errors["detail"] = "Nothing to update."
    if errors:
        return None, errors
    return attrs, None


def _goal_queryset(profile):
    return LearningGoal.objects.filter(profile=profile).select_related("topic", "path")


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningProfileThrottle])
def learner_goals(request):
    profile = request.learning_profile
    if request.method == "GET":
        queryset = _goal_queryset(profile)
        state = request.query_params.get("state")
        if state:
            valid_states = {value for value, _label in LearningGoal.STATES}
            if state not in valid_states:
                return Response({"detail": "Invalid goal state filter."}, status=400)
            queryset = queryset.filter(state=state)
        rows = list(queryset.order_by("state", "target_date", "created_at", "pk")[:MAX_LIST_RESULTS + 1])
        truncated = len(rows) > MAX_LIST_RESULTS
        serialized_rows = rows[:MAX_LIST_RESULTS]
        age = _age_for_profile(profile)
        candidates = _language_candidates(_goal_language(profile))
        visible_topics, visible_paths = _goal_link_maps(profile, serialized_rows, age, candidates)
        return Response({
            "results": [
                _goal_json(goal, profile, visible_topics, visible_paths)
                for goal in serialized_rows
            ],
            "truncated": truncated,
        })

    with transaction.atomic():
        profile = LearningProfile.objects.select_for_update().get(
            pk=profile.pk, user=request.user,
        )
        age = _age_for_profile(profile)
        candidates = _language_candidates(_goal_language(profile))
        attrs, errors = _validate_goal_data(
            request.data, profile, lock=True, age=age, candidates=candidates,
        )
        if errors:
            return Response({"errors": errors}, status=400)
        goal = LearningGoal(profile=profile, **attrs)
        try:
            goal.full_clean()
        except DjangoValidationError as exc:
            detail = getattr(exc, "message_dict", {"detail": exc.messages})
            return Response({"errors": detail}, status=400)
        goal.state = "active"
        goal.closed_at = None
        goal.save()
    return Response(_goal_json(goal, profile), status=201)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningProfileThrottle])
def learner_goal_detail(request, goal_id):
    profile = request.learning_profile
    if request.method == "GET":
        goal = _goal_queryset(profile).filter(pk=goal_id).first()
        if goal is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(_goal_json(goal, profile))

    with transaction.atomic():
        # Avoid locking nullable topic/path outer joins on PostgreSQL.
        goal = LearningGoal.objects.filter(
            profile=profile, pk=goal_id,
        ).select_for_update().first()
        if goal is None:
            return Response({"detail": "Not found."}, status=404)
        if request.method == "DELETE":
            if goal.state != "closed":
                goal.state = "closed"
                goal.closed_at = timezone.now()
                goal.save(update_fields=["state", "closed_at", "updated_at"])
            return Response(status=204)

        age = _age_for_profile(profile)
        candidates = _language_candidates(_goal_language(profile))
        attrs, errors = _validate_goal_data(
            request.data, profile, instance=goal, lock=True,
            age=age, candidates=candidates,
        )
        if errors:
            return Response({"errors": errors}, status=400)
        for field, value in attrs.items():
            setattr(goal, field, value)
        if goal.state in TERMINAL_STATES:
            goal.closed_at = goal.closed_at or timezone.now()
        else:
            goal.closed_at = None
        try:
            goal.full_clean()
        except DjangoValidationError as exc:
            detail = getattr(exc, "message_dict", {"detail": exc.messages})
            return Response({"errors": detail}, status=400)
        goal.save()
    return Response(_goal_json(goal, profile))
