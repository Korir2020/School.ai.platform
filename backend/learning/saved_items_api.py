"""Learner-owned saves for currently visible learning resources and paths."""

import re

from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .catalog_api import (
    MAX_RESULTS,
    _age_for_profile,
    _language_candidates,
    _path_is_visible,
    _path_json,
    _path_queryset,
    _requested_language,
    _resource_is_visible,
    _resource_json,
    _resource_queryset,
    _allowed_query_keys,
)
from .models import LearningProfile, SavedLearningItem
from .permissions import ActiveLearnerSelfService
from .throttles import LearningCatalogThrottle


MAX_SAVED_RESULTS = MAX_RESULTS
MAX_DATABASE_ID = 9_223_372_036_854_775_807
POSITIVE_INTEGER_RE = re.compile(r"^[1-9]\d*$")


def _parse_item_reference(data):
    """Return exactly one well-formed resource/path reference or an error."""
    if not hasattr(data, "keys"):
        return None, {"detail": "Send a JSON object."}
    allowed = {"resource_id", "path_id"}
    errors = {
        key: "This field is unsupported."
        for key in set(data.keys()) - allowed
    }
    present = [key for key in allowed if key in data]
    if len(present) != 1:
        errors["detail"] = "Provide exactly one of resource_id or path_id."
        return None, errors

    field = present[0]
    value = data.get(field)
    if isinstance(value, bool):
        errors[field] = "Use a positive integer ID."
    elif isinstance(value, int):
        if value <= 0 or value > MAX_DATABASE_ID:
            errors[field] = "Use a positive integer ID."
    elif (
        isinstance(value, str)
        and len(value) <= 19
        and POSITIVE_INTEGER_RE.fullmatch(value)
    ):
        value = int(value)
        if value > MAX_DATABASE_ID:
            errors[field] = "Use a positive integer ID."
    else:
        errors[field] = "Use a positive integer ID."

    if errors:
        return None, errors
    return ("resource" if field == "resource_id" else "path", value), None


def _visible_item(profile, item_type, item_id, age, candidates):
    """Resolve an item only through the same eligibility rules as the catalogue."""
    if item_type == "resource":
        item = _resource_queryset(profile, age, candidates).filter(pk=item_id).first()
        if item is None or not _resource_is_visible(profile, item, age, candidates):
            return None
        return item

    item = _path_queryset(profile, age, candidates).filter(pk=item_id).first()
    if item is None or not _path_is_visible(profile, item, age, candidates):
        return None
    return item


def _saved_json(saved, item, item_type, language, profile, age):
    if item_type == "resource":
        serialized = _resource_json(item, language, age)
    else:
        serialized = _path_json(item, profile, language, age)
    return {
        "id": saved.pk,
        "item_type": item_type,
        "item_id": item.pk,
        "saved_at": saved.saved_at,
        "item": serialized,
    }


def _language_and_context(request, profile):
    error = _allowed_query_keys(request, {"lang"})
    if error:
        return None, None, None, error
    language, error = _requested_language(request, profile)
    if error:
        return None, None, None, error
    age = _age_for_profile(profile)
    return language, age, _language_candidates(language), None


@extend_schema_view(
    get=extend_schema(operation_id="learning_saved_items_list"),
    post=extend_schema(operation_id="learning_saved_items_create"),
    delete=extend_schema(operation_id="learning_saved_items_remove_by_target"),
)
@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningCatalogThrottle])
def learner_saved_items(request):
    """List, save, or remove one of the caller's currently visible catalogue items.

    POST and DELETE use a JSON object containing exactly one of ``resource_id``
    or ``path_id``. Repeating either operation is safe. DELETE intentionally
    succeeds when the matching save is already absent or its content has since
    become hidden, so learners can clear stale saves without exposing them.
    """
    profile = request.learning_profile
    language, age, candidates, error = _language_and_context(request, profile)
    if error:
        return error

    if request.method == "GET":
        rows = list(
            SavedLearningItem.objects.filter(profile=profile)
            .select_related("resource", "path")
            .order_by("-saved_at", "-pk")[:MAX_SAVED_RESULTS + 1]
        )
        truncated = len(rows) > MAX_SAVED_RESULTS
        rows = rows[:MAX_SAVED_RESULTS]

        resource_ids = {row.resource_id for row in rows if row.resource_id}
        path_ids = {row.path_id for row in rows if row.path_id}
        resources = {
            item.pk: item
            for item in _resource_queryset(profile, age, candidates).filter(pk__in=resource_ids)
        }
        paths = {
            item.pk: item
            for item in _path_queryset(profile, age, candidates).filter(pk__in=path_ids)
        }

        results = []
        for saved in rows:
            if saved.resource_id:
                item = resources.get(saved.resource_id)
                if item is None or not _resource_is_visible(profile, item, age, candidates):
                    continue
                item_type = "resource"
            else:
                item = paths.get(saved.path_id)
                if item is None or not _path_is_visible(profile, item, age, candidates):
                    continue
                item_type = "path"
            results.append(_saved_json(saved, item, item_type, language, profile, age))

        return Response({
            "results": results,
            "truncated": truncated,
            "language": language,
        })

    reference, errors = _parse_item_reference(request.data)
    if errors:
        return Response({"errors": errors}, status=400)
    item_type, item_id = reference
    field = "resource" if item_type == "resource" else "path"

    if request.method == "DELETE":
        # Filtering by the caller's profile makes this an idempotent no-op for
        # absent, stale, and other learners' saves alike.
        SavedLearningItem.objects.filter(
            profile=profile,
            **{f"{field}_id": item_id},
        ).delete()
        return Response(status=204)

    with transaction.atomic():
        # Serialize concurrent save attempts for this profile, then re-resolve
        # the catalogue item immediately before writing. Authority is always
        # derived from the authenticated user's own LearningProfile.
        locked_profile = LearningProfile.objects.select_for_update().filter(
            pk=profile.pk,
            user=request.user,
        ).first()
        if locked_profile is None:
            return Response({"detail": "Not found."}, status=404)
        item = _visible_item(locked_profile, item_type, item_id, age, candidates)
        if item is None:
            return Response({"detail": "Learning item is not available."}, status=404)

        saved, created = SavedLearningItem.objects.get_or_create(
            profile=locked_profile,
            **{field: item},
        )
        data = _saved_json(saved, item, item_type, language, locked_profile, age)
    return Response(data, status=201 if created else 200)


@extend_schema(operation_id="learning_saved_item_remove_by_id")
@api_view(["DELETE"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningCatalogThrottle])
def learner_saved_item_detail(request, saved_item_id):
    """Remove one saved-record ID, concealing records owned by other learners."""
    with transaction.atomic():
        saved = SavedLearningItem.objects.select_for_update().filter(
            profile=request.learning_profile,
            pk=saved_item_id,
        ).first()
        if saved is None:
            return Response({"detail": "Not found."}, status=404)
        saved.delete()
    return Response(status=204)
