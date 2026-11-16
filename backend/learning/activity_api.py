"""Validated learner path participation and private activity history APIs."""

import json
import re
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .catalog_api import (
    _approved_translations,
    _age_for_profile,
    _language_candidates,
    _normalize_language,
    _path_is_visible,
    _path_queryset,
    _requested_language,
    _resource_is_visible,
    _resource_queryset,
)
from .models import (
    LearningActivityEvent,
    LearningPath,
    LearningPathItem,
    LearningPathParticipation,
    LearningResource,
)
from .permissions import ActiveLearnerSelfService
from .throttles import LearningActivityThrottle

MAX_EVENT_BODY_BYTES = 8192
MAX_HISTORY_RESULTS = 200
ALLOWED_CHECKPOINTS = {"attempted", "reviewed", "needs_help", "understood"}
ALLOWED_CLIENT_EVENT_TYPES = {"started", "progress", "feedback"}


def _json_object(request, *, max_bytes=MAX_EVENT_BODY_BYTES):
    raw = request.body or b""
    if len(raw) > max_bytes:
        return None, Response({"code": "payload_too_large", "detail": "Request body exceeds the learning API size limit."}, status=413)
    try:
        data = request.data
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None, Response({"code": "invalid_json", "detail": "Send a valid JSON object."}, status=400)
    if not isinstance(data, dict):
        return None, Response({"code": "invalid_payload", "detail": "Send a JSON object."}, status=400)
    return data, None


def _learner_language(request, profile):
    language, error = _requested_language(request, profile)
    if error is not None:
        return None, None, error
    normalized = _normalize_language(language)
    if normalized is None:
        return None, None, Response({"detail": "A valid learning language is required."}, status=400)
    return normalized, _language_candidates(normalized), None


def _event_json(event):
    target = None
    if event.resource_id:
        target = {"type": "resource", "id": event.resource_id}
    elif event.path_item_id:
        target = {
            "type": "path_item",
            "id": event.path_item_id,
            "path_id": event.path_item.path_id,
        }
    return {
        "id": event.pk,
        "event_type": event.event_type,
        "target": target,
        "occurred_at": event.occurred_at,
        "details": event.details,
    }


def _valid_event(data):
    allowed = {"idempotency_key", "event_type", "resource_id", "path_item_id", "details"}
    if set(data) - allowed:
        return None, "Unsupported event fields are not accepted."
    key = data.get("idempotency_key")
    try:
        key = uuid.UUID(str(key))
    except (TypeError, ValueError, AttributeError):
        return None, "A UUID idempotency_key is required."
    event_type = data.get("event_type")
    if not isinstance(event_type, str):
        return None, "event_type must be a supported string value."
    if event_type in {"completed", "submitted"}:
        return None, "Completion and work-submission events require server-verifiable evidence and are not client-submittable."
    if event_type not in ALLOWED_CLIENT_EVENT_TYPES:
        return None, "Unsupported activity event type."
    target_keys = [name for name in ("resource_id", "path_item_id") if name in data]
    if len(target_keys) != 1:
        return None, "Exactly one resource_id or path_item_id is required."
    target_key = target_keys[0]
    target_id = data[target_key]
    if isinstance(target_id, bool) or not isinstance(target_id, int) or target_id <= 0:
        return None, "The target ID must be a positive integer."
    details = data.get("details", {})
    if not isinstance(details, dict):
        return None, "details must be a JSON object."
    if event_type == "started" and details:
        return None, "Started events do not accept client-supplied details."
    if event_type == "progress":
        checkpoint = details.get("checkpoint")
        if set(details) != {"checkpoint"} or not isinstance(checkpoint, str) or checkpoint not in ALLOWED_CHECKPOINTS:
            return None, "Progress details must contain one supported checkpoint value."
    if event_type == "feedback":
        rating = details.get("rating")
        if set(details) != {"rating"} or isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            return None, "Feedback details must contain only an integer rating from 1 to 5."
    return {
        "idempotency_key": key,
        "event_type": event_type,
        "target_key": target_key,
        "target_id": target_id,
        "details": details,
    }, None


def _visible_path(profile, path_id, age, candidates):
    path = _path_queryset(profile, age, candidates).filter(pk=path_id).first()
    if path is None or not _path_is_visible(profile, path, age, candidates):
        return None
    return path


def _visible_resource(profile, resource_id, age, candidates):
    resource = _resource_queryset(profile, age, candidates).filter(pk=resource_id).first()
    if resource is None or not _resource_is_visible(profile, resource, age, candidates):
        return None
    return resource


def _locked_visible_resource(profile, resource_id, age, candidates):
    resource = LearningResource.objects.select_for_update().filter(pk=resource_id).first()
    if resource is None:
        return None
    resource.catalog_translations = list(
        _approved_translations(candidates).filter(resource_id=resource.pk)
    )
    if not _resource_is_visible(profile, resource, age, candidates):
        return None
    return resource


def _locked_visible_path(profile, path_id, age, candidates):
    """Lock and revalidate every row that determines a path's learner visibility."""
    path = LearningPath.objects.select_for_update().filter(pk=path_id).first()
    if path is None:
        return None
    items = list(
        LearningPathItem.objects.select_for_update().filter(path_id=path.pk).order_by("pk")
    )
    resource_ids = sorted({item.resource_id for item in items if item.resource_id})
    resources = {
        resource.pk: resource
        for resource in LearningResource.objects.select_for_update()
        .filter(pk__in=resource_ids).order_by("pk")
    }
    translations = _approved_translations(candidates).filter(resource_id__in=resource_ids)
    translations_by_resource = {}
    for translation in translations:
        translations_by_resource.setdefault(translation.resource_id, []).append(translation)
    for item in items:
        if item.resource_id:
            resource = resources.get(item.resource_id)
            if resource is None:
                return None
            resource.catalog_translations = translations_by_resource.get(resource.pk, [])
            item.resource = resource
    path.catalog_items = items
    if not _path_is_visible(profile, path, age, candidates):
        return None
    return path


@api_view(["POST"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
@throttle_classes([LearningActivityThrottle])
def start_path_participation(request, path_id):
    """Idempotently follow the currently visible, published path version."""
    data, error = _json_object(request)
    if error is not None:
        return error
    if data:
        return Response({"detail": "Path start does not accept client-supplied progress or completion fields."}, status=400)
    language, candidates, error = _learner_language(request, request.learning_profile)
    if error is not None:
        return error
    age = _age_for_profile(request.learning_profile)
    with transaction.atomic():
        path = _locked_visible_path(request.learning_profile, path_id, age, candidates)
        if path is None:
            return Response({"detail": "Learning path not found."}, status=404)
        participation, created = LearningPathParticipation.objects.get_or_create(
            profile=request.learning_profile,
            path=path,
            path_version=path.version,
            defaults={"state": "in_progress"},
        )
    return Response({
        "id": participation.pk,
        "path_id": path.pk,
        "path_version": participation.path_version,
        "state": participation.state,
        "started_at": participation.started_at,
        "last_activity_at": participation.last_activity_at,
        "completed_at": participation.completed_at,
        "completion_policy": "No server-verifiable completion rule is currently configured; client events cannot mark a path complete.",
    }, status=201 if created else 200)


@api_view(["GET"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
@throttle_classes([LearningActivityThrottle])
def learner_path_participations(request):
    """List only this learner's participations for paths currently visible to them."""
    if set(request.query_params) - {"limit", "lang"}:
        return Response({"detail": "Unsupported participation filter."}, status=400)
    raw_limit = request.query_params.get("limit", str(MAX_HISTORY_RESULTS))
    if not re.fullmatch(r"[1-9]\d{0,2}", raw_limit):
        return Response({"detail": "limit must be between 1 and 200."}, status=400)
    limit = min(int(raw_limit), MAX_HISTORY_RESULTS)
    profile = request.learning_profile
    _language, candidates, error = _learner_language(request, profile)
    if error is not None:
        return error
    age = _age_for_profile(profile)
    rows = list(
        LearningPathParticipation.objects.filter(profile=profile)
        .select_related("path")
        .order_by("-started_at", "-id")[: limit * 2 + 1]
    )
    visible = []
    for row in rows:
        path = _visible_path(profile, row.path_id, age, candidates)
        if path is None:
            continue
        visible.append({
            "id": row.pk,
            "path_id": path.pk,
            "path_title": path.title,
            "path_version": row.path_version,
            "state": row.state,
            "started_at": row.started_at,
            "last_activity_at": row.last_activity_at,
            "completed_at": row.completed_at,
        })
        if len(visible) >= limit:
            break
    return Response({"results": visible, "truncated": len(rows) > limit})


@api_view(["GET", "POST"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
@throttle_classes([LearningActivityThrottle])
def learner_activity_events(request):
    """Record small validated self-assessment events and read private learner history."""
    profile = request.learning_profile
    if request.method == "GET":
        if set(request.query_params) - {"limit"}:
            return Response({"detail": "Unsupported activity-history filter."}, status=400)
        raw_limit = request.query_params.get("limit", str(MAX_HISTORY_RESULTS))
        if not re.fullmatch(r"[1-9]\d{0,2}", raw_limit):
            return Response({"detail": "limit must be between 1 and 200."}, status=400)
        limit = min(int(raw_limit), MAX_HISTORY_RESULTS)
        events = list(
            LearningActivityEvent.objects.filter(profile=profile)
            .select_related("resource", "path_item__path")
            .order_by("-occurred_at", "-id")[: limit + 1]
        )
        return Response({
            "results": [_event_json(event) for event in events[:limit]],
            "truncated": len(events) > limit,
        })

    if request.query_params:
        return Response({"detail": "Activity events do not accept query parameters on POST."}, status=400)
    data, error = _json_object(request)
    if error is not None:
        return error
    event_data, message = _valid_event(data)
    if message:
        return Response({"detail": message}, status=400)

    language, candidates, error = _learner_language(request, profile)
    if error is not None:
        return error
    age = _age_for_profile(profile)
    resource = None
    path_item = None
    participation = None
    with transaction.atomic():
        if event_data["target_key"] == "resource_id":
            resource = _locked_visible_resource(profile, event_data["target_id"], age, candidates)
            if resource is None:
                return Response({"detail": "Learning resource not found."}, status=404)
        else:
            path_id = LearningPathItem.objects.filter(pk=event_data["target_id"]).values_list("path_id", flat=True).first()
            if path_id is None:
                return Response({"detail": "Path item not found."}, status=404)
            path = _locked_visible_path(profile, path_id, age, candidates)
            if path is None:
                return Response({"detail": "Path item not found."}, status=404)
            path_item = next((item for item in path.catalog_items if item.pk == event_data["target_id"]), None)
            if path_item is None:
                return Response({"detail": "Path item not found."}, status=404)
            participation = LearningPathParticipation.objects.select_for_update().filter(
                profile=profile, path=path, path_version=path.version, state="in_progress",
            ).first()
            if participation is None:
                return Response({"detail": "Start this visible path before recording path-item activity."}, status=409)

        existing = LearningActivityEvent.objects.filter(
            profile=profile, idempotency_key=event_data["idempotency_key"],
        ).first()
        if existing is not None:
            same = (
                existing.event_type == event_data["event_type"]
                and existing.resource_id == (resource.pk if resource else None)
                and existing.path_item_id == (path_item.pk if path_item else None)
                and existing.details == event_data["details"]
                and existing.duration_seconds is None
            )
            if not same:
                return Response({"code": "idempotency_conflict", "detail": "This idempotency key was already used for a different event."}, status=409)
            return Response(_event_json(existing), status=200)
        try:
            with transaction.atomic():
                event = LearningActivityEvent.objects.create(
                    profile=profile,
                    event_type=event_data["event_type"],
                    resource=resource,
                    path_item=path_item,
                    occurred_at=timezone.now(),
                    idempotency_key=event_data["idempotency_key"],
                    duration_seconds=None,
                    details=event_data["details"],
                )
        except IntegrityError:
            existing = LearningActivityEvent.objects.filter(
                profile=profile, idempotency_key=event_data["idempotency_key"],
            ).first()
            if existing is None:
                raise
            same = (
                existing.event_type == event_data["event_type"]
                and existing.resource_id == (resource.pk if resource else None)
                and existing.path_item_id == (path_item.pk if path_item else None)
                and existing.details == event_data["details"]
            )
            if not same:
                return Response({"code": "idempotency_conflict", "detail": "This idempotency key was already used for a different event."}, status=409)
            return Response(_event_json(existing), status=200)
        if participation is not None:
            participation.last_activity_at = event.occurred_at
            participation.save(update_fields=["last_activity_at"])
    return Response(_event_json(event), status=201)
