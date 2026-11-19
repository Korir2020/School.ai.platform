"""School-scoped learning-content governance APIs.

Publishing remains deliberately disabled in code until licensing, moderation,
shared-catalogue ownership, and publication policies receive explicit approval.
No endpoint fetches external URLs or imports content from third-party sites.
"""

import json
import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .catalog_api import _normalize_language
from .models import (
    LearningContentRevision,
    LearningFramework,
    LearningPath,
    LearningPathItem,
    LearningPathTranslation,
    LearningResource,
    LearningResourceTranslation,
    LearningTopic,
    LearningAuditEvent,
)
from .quiz_schema import QuizSchemaError, normalize_practice_quiz
from .permissions import FullSchoolContentReviewer, SchoolContentAuthor
from .throttles import LearningContentThrottle

MAX_CONTENT_BODY_BYTES = 65536
MAX_TEXT_BODY = 24000
MAX_LIST = 50
# This is intentionally not an environment flag: a deploy-time setting must not
# bypass unapproved rights, moderation, and shared-catalogue ownership policies.
PUBLICATION_POLICY_APPROVED = False

RESOURCE_INPUTS = {
    "title", "summary", "body", "resource_type", "origin", "external_url",
    "language_code", "difficulty", "access_tier", "age_min", "age_max", "framework_ids",
    "topic_ids", "source_name", "license_name", "license_url", "attribution",
    "rights_notes", "practice_quiz",
}
PATH_INPUTS = {
    "title", "description", "objectives", "language_code", "difficulty", "access_tier",
    "age_min", "age_max", "framework_ids", "topic_ids", "items",
    "source_name", "license_name", "license_url", "attribution", "rights_notes",
}


def _body_object(request):
    if len(request.body or b"") > MAX_CONTENT_BODY_BYTES:
        return None, Response({"code": "payload_too_large", "detail": "Content request exceeds the size limit."}, status=413)
    try:
        data = request.data
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None, Response({"detail": "Send a valid JSON object."}, status=400)
    if not isinstance(data, dict):
        return None, Response({"detail": "Send a JSON object."}, status=400)
    return data, None


def _actor(request):
    return request.learning_content_actor


def _is_admin(request):
    return request.learning_content_role == "school_admin"


def _resource_queryset(request):
    query = LearningResource.objects.filter(scope="school", school_id=_actor(request).school_id)
    if not _is_admin(request):
        query = query.filter(author=request.user)
    return query.select_related("author", "school", "reviewed_by").prefetch_related("topics", "frameworks")


def _path_queryset(request):
    query = LearningPath.objects.filter(scope="school", school_id=_actor(request).school_id)
    if not _is_admin(request):
        query = query.filter(author=request.user)
    return query.select_related("author", "school", "reviewed_by").prefetch_related("topics", "frameworks", "items__resource")


def _can_manage(request, obj):
    if obj.scope != "school" or obj.school_id != _actor(request).school_id:
        return False
    return _is_admin(request) or obj.author_id == request.user.pk


def _clean_text(value, name, *, maximum, required=False, plain=True):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text.")
    value = value.strip()
    if plain:
        value = strip_tags(value)
    if len(value) > maximum:
        raise ValueError(f"{name} exceeds the {maximum}-character limit.")
    if required and not value:
        raise ValueError(f"{name} is required.")
    return value


def _age_value(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 120:
        raise ValueError(f"{name} must be an integer from 0 to 120 or null.")
    return value


def _relationship_ids(value, model, label):
    if not isinstance(value, list) or len(value) > MAX_LIST:
        raise ValueError(f"{label} must be a list of at most {MAX_LIST} active IDs.")
    if any(isinstance(pk, bool) or not isinstance(pk, int) or pk <= 0 for pk in value):
        raise ValueError(f"{label} must contain positive integer IDs.")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} must not contain duplicate IDs.")
    rows = list(model.objects.filter(pk__in=value, is_active=True))
    if len(rows) != len(value):
        raise ValueError(f"Every {label[:-3].lower()} must exist and be active.")
    return rows


def _https(value, name, *, required=False):
    if not value:
        if required:
            raise ValueError(f"{name} must be an HTTPS URL.")
        return ""
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError(f"{name} must be an HTTPS URL of at most 1000 characters.")
    try:
        URLValidator(schemes=["https"])(value)
    except DjangoValidationError:
        raise ValueError(f"{name} must be an HTTPS URL.")
    return value


def _license_error(obj):
    """Allow PD/CC0, CC BY, CC BY-SA; reject NC/ND; others need a note."""
    import re as _re

    tokens = _re.findall(r"[a-z0-9]+", (obj.license_name or "").lower())
    squashed = "".join(tokens)
    if (
        "nc" in tokens
        or "nd" in tokens
        or "noncommercial" in squashed
        or "noderiv" in squashed
    ):
        return "CC BY-NC and CC BY-ND licences are not accepted."
    core = [t for t in tokens if not t.isdigit()]
    if (
        core in (["cc", "by"], ["cc", "by", "sa"])
        or "cc0" in core
        or core[:2] == ["public", "domain"]
        or core[:2] == ["marian", "owned"]
    ):
        return None
    if not (obj.rights_notes or "").strip():
        return "Other licences need a recorded permission note in rights notes."
    return None


def _source_error(obj):
    """Stage 2: source type, licence expiry and evidence for each source type."""
    from datetime import date
    if not hasattr(obj, "source_type"):
        return None
    kind = obj.source_type
    if obj.scope == "public" and not kind:
        return "Choose a source type before submission."
    if obj.license_expires_on and obj.license_expires_on < date.today():
        return "The recorded licence has expired. Renew it before submission."
    if kind == "open_licensed" and not (obj.license_url or "").strip():
        return "Open-licensed content needs the licence URL."
    if kind == "commercial_permission" and not (obj.rights_notes or "").strip():
        return "Commercial content needs the written permission recorded in rights notes."
    return None


def _metadata_error(obj):
    if not obj.source_name.strip():
        return "Record the content provenance/source before submission."
    if not (obj.license_name.strip() or obj.rights_notes.strip()):
        return "Record the licence or documented usage rights before submission."
    licence_problem = _license_error(obj)
    if licence_problem:
        return licence_problem
    source_problem = _source_error(obj)
    if source_problem:
        return source_problem
    if not obj.attribution.strip():
        return "Record attribution before submission."
    if not _normalize_language(obj.language_code):
        return "Use a valid language code before submission."
    if obj.age_min is not None and obj.age_max is not None and obj.age_min > obj.age_max:
        return "The minimum age must not exceed the maximum age."
    if isinstance(obj, LearningResource):
        if obj.private_assets.exclude(scan_state="deleted").exclude(
            scan_state="clean", deleted_at__isnull=True,
        ).exists():
            return "Every active attachment must pass the configured malware scanner before submission or review."
        if obj.origin == "external":
            if not obj.external_url.startswith("https://"):
                return "External resources require an HTTPS source URL."
            if obj.body.strip():
                return "External resources may link to original material but must not copy third-party content into Marian."
        if obj.resource_type == "external_link" and not obj.external_url.startswith("https://"):
            return "External-link resources require an HTTPS URL."
        if obj.resource_type == "interactive":
            try:
                normalize_practice_quiz(obj.practice_quiz)
            except QuizSchemaError as exc:
                return str(exc)
        elif obj.practice_quiz not in ({}, None):
            return "Practice quiz content is only supported for interactive resources."
        unreviewed = obj.translations.exclude(
            review_state="approved", reviewed_by__isnull=False, reviewed_at__isnull=False,
        )
        # Draft translations may remain private; in-review text must be resolved
        # before the source can be approved. Only approved translations can later
        # be offered to learners.
        if unreviewed.filter(review_state="in_review").exists():
            return "Resolve translations currently awaiting review before submitting the source resource."
    elif isinstance(obj, LearningPath):
        if obj.translations.filter(review_state="in_review").exists():
            return "Resolve path translations currently awaiting review before submitting the source path."
    try:
        obj.full_clean(exclude=["frameworks", "topics", "reviewed_by"])
    except DjangoValidationError as exc:
        return "Content metadata is invalid: " + "; ".join(
            str(item) for values in exc.message_dict.values() for item in values
        ) if hasattr(exc, "message_dict") else "Content metadata is invalid."
    return None


def _path_items_error(path):
    for item in path.items.select_related("resource").all():
        if item.completion_rule != "view":
            return "Only the non-completing 'view' rule is currently supported; verifiable completion rules are not configured."
        if item.resource_id:
            resource = item.resource
            if (
                resource.status != "published" or resource.published_at is None
                or resource.reviewed_by_id is None or resource.reviewed_at is None
                or resource.retired_at is not None
                or resource.language_code.lower() != path.language_code.lower()
                or not (resource.scope == "public" or resource.school_id == path.school_id)
            ):
                return "Path items may reference only currently published, reviewed resources in this school's or the shared scope and matching language."
    return None


def _audit(request, obj, action, **safe_details):
    LearningAuditEvent.objects.create(
        actor=request.user,
        school=_actor(request).school,
        scope="school",
        action=action,
        target_type="resource" if isinstance(obj, LearningResource) else "path",
        target_id=str(obj.pk),
        safe_details=safe_details,
    )


def _resource_snapshot(obj):
    return {
        "kind": "resource", "id": obj.pk, "version": obj.version,
        "title": obj.title, "summary": obj.summary, "body": obj.body,
        "practice_quiz": obj.practice_quiz,
        "resource_type": obj.resource_type, "origin": obj.origin,
        "external_url": obj.external_url, "language_code": obj.language_code,
        "difficulty": obj.difficulty, "access_tier": obj.access_tier,
        "age_min": obj.age_min, "age_max": obj.age_max,
        "framework_ids": sorted(obj.frameworks.values_list("id", flat=True)),
        "topic_ids": sorted(obj.topics.values_list("id", flat=True)),
        "source_name": obj.source_name, "license_name": obj.license_name,
        "license_url": obj.license_url, "attribution": obj.attribution,
        "rights_notes": obj.rights_notes,
        "source_type": obj.source_type,
        "license_expires_on": obj.license_expires_on.isoformat() if obj.license_expires_on else None,
        "license_verified_at": obj.license_verified_at.isoformat() if obj.license_verified_at else None,
        "private_assets": [
            {"id": asset.pk, "content_type": asset.content_type,
             "size_bytes": asset.size_bytes, "scan_state": asset.scan_state}
            for asset in obj.private_assets.exclude(scan_state="deleted").order_by("id")
        ],
        "translations": [
            {"id": tr.pk, "language_code": tr.language_code, "title": tr.title,
             "summary": tr.summary, "body": tr.body, "source": tr.translation_source,
             "review_state": tr.review_state}
            for tr in obj.translations.order_by("language_code")
        ],
    }


def _path_snapshot(obj):
    return {
        "kind": "path", "id": obj.pk, "version": obj.version,
        "title": obj.title, "description": obj.description,
        "objectives": obj.objectives, "language_code": obj.language_code,
        "difficulty": obj.difficulty, "access_tier": obj.access_tier,
        "age_min": obj.age_min, "age_max": obj.age_max,
        "framework_ids": sorted(obj.frameworks.values_list("id", flat=True)),
        "topic_ids": sorted(obj.topics.values_list("id", flat=True)),
        "origin": obj.origin, "source_name": obj.source_name,
        "license_name": obj.license_name, "license_url": obj.license_url,
        "attribution": obj.attribution, "rights_notes": obj.rights_notes,
        "translations": [
            {"id": tr.pk, "language_code": tr.language_code, "title": tr.title,
             "description": tr.description, "objectives": tr.objectives,
             "source": tr.translation_source, "review_state": tr.review_state}
            for tr in obj.translations.order_by("language_code")
        ],
        "items": [
            {"position": item.position, "item_type": item.item_type,
             "resource_id": item.resource_id, "title": item.title,
             "instructions": item.instructions, "completion_rule": item.completion_rule}
            for item in obj.items.select_related("resource").order_by("position")
        ],
    }


def _record_revision(obj, user):
    snapshot = _resource_snapshot(obj) if isinstance(obj, LearningResource) else _path_snapshot(obj)
    return LearningContentRevision.objects.create(
        resource=obj if isinstance(obj, LearningResource) else None,
        path=obj if isinstance(obj, LearningPath) else None,
        version=obj.version,
        snapshot=snapshot,
        created_by=user,
    )


def _resource_json(obj):
    return {
        "id": obj.pk, "scope": obj.scope, "school_id": obj.school_id,
        "title": obj.title, "summary": obj.summary, "body": obj.body,
        "practice_quiz": obj.practice_quiz,
        "source_type": obj.source_type,
        "license_expires_on": str(obj.license_expires_on) if obj.license_expires_on else None,
        "license_verified_by_id": obj.license_verified_by_id,
        "license_verified_at": obj.license_verified_at,
        "resource_type": obj.resource_type, "origin": obj.origin,
        "external_url": obj.external_url, "language_code": obj.language_code,
        "difficulty": obj.difficulty, "access_tier": obj.access_tier,
        "age_min": obj.age_min, "age_max": obj.age_max,
        "framework_ids": list(obj.frameworks.values_list("id", flat=True)),
        "topic_ids": list(obj.topics.values_list("id", flat=True)),
        "source_name": obj.source_name, "license_name": obj.license_name,
        "license_url": obj.license_url, "attribution": obj.attribution,
        "rights_notes": obj.rights_notes, "author_id": obj.author_id,
        "status": obj.status, "version": obj.version,
        "reviewed_by_id": obj.reviewed_by_id, "reviewed_at": obj.reviewed_at,
        "published_at": obj.published_at, "retired_at": obj.retired_at,
        "created_at": obj.created_at, "updated_at": obj.updated_at,
    }


def _path_json(obj):
    return {
        "id": obj.pk, "scope": obj.scope, "school_id": obj.school_id,
        "title": obj.title, "description": obj.description,
        "objectives": obj.objectives, "language_code": obj.language_code,
        "difficulty": obj.difficulty, "access_tier": obj.access_tier,
        "age_min": obj.age_min, "age_max": obj.age_max,
        "framework_ids": list(obj.frameworks.values_list("id", flat=True)),
        "topic_ids": list(obj.topics.values_list("id", flat=True)),
        "source_name": obj.source_name, "license_name": obj.license_name,
        "license_url": obj.license_url, "attribution": obj.attribution,
        "rights_notes": obj.rights_notes, "origin": obj.origin,
        "author_id": obj.author_id, "status": obj.status, "version": obj.version,
        "items": [
            {"id": item.pk, "position": item.position, "item_type": item.item_type,
             "resource_id": item.resource_id, "title": item.title,
             "instructions": item.instructions, "completion_rule": item.completion_rule}
            for item in obj.items.select_related("resource").order_by("position")
        ],
        "reviewed_by_id": obj.reviewed_by_id, "reviewed_at": obj.reviewed_at,
        "published_at": obj.published_at, "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


RESOURCE_INPUTS = RESOURCE_INPUTS | {"source_type", "license_expires_on"}


def _set_resource_fields(obj, data):
    unknown = set(data) - RESOURCE_INPUTS
    if unknown:
        raise ValueError("Unsupported resource fields: " + ", ".join(sorted(unknown)))
    for name, maximum, required in (
        ("title", 240, True), ("summary", 4000, False),
        ("body", MAX_TEXT_BODY, False), ("source_name", 240, False),
        ("license_name", 160, False), ("attribution", 4000, False),
        ("rights_notes", 5000, False),
    ):
        if name in data:
            setattr(obj, name, _clean_text(data[name], name, maximum=maximum, required=required))
    for name, choices in (("resource_type", {key for key, _ in LearningResource.RESOURCE_TYPES}),
                          ("origin", {key for key, _ in LearningResource.ORIGINS}),
                          ("access_tier", {key for key, _ in LearningResource.ACCESS_TIERS}),
                          ("difficulty", {"", *(key for key, _ in LearningResource.DIFFICULTIES)})):
        if name in data:
            if not isinstance(data[name], str) or data[name] not in choices:
                raise ValueError(f"Invalid {name}.")
            setattr(obj, name, data[name])
    if "language_code" in data:
        language = _normalize_language(data["language_code"])
        if language is None:
            raise ValueError("Use a valid language code, such as en or sw.")
        obj.language_code = language
    for field in ("age_min", "age_max"):
        if field in data:
            setattr(obj, field, _age_value(data[field], field))
    if "external_url" in data:
        obj.external_url = _https(data["external_url"], "external_url")
    if "license_url" in data:
        obj.license_url = _https(data["license_url"], "license_url")
    if "source_type" in data:
        if data["source_type"] not in {""} | {key for key, _ in LearningResource.SOURCE_TYPES}:
            raise ValueError("Invalid source_type.")
        obj.source_type = data["source_type"]
    if "license_expires_on" in data:
        from datetime import date as _date
        value = data["license_expires_on"]
        if value in (None, ""):
            obj.license_expires_on = None
        else:
            try:
                obj.license_expires_on = _date.fromisoformat(value)
            except (TypeError, ValueError):
                raise ValueError("Use a licence expiry date like 2027-01-31.")
    if "practice_quiz" in data:
        if obj.resource_type == "interactive":
            obj.practice_quiz = normalize_practice_quiz(
                data["practice_quiz"], allow_incomplete=True,
            )
        elif data["practice_quiz"] not in ({}, None):
            raise ValueError("Practice quiz content is only supported for interactive resources.")
        else:
            obj.practice_quiz = {}
    if obj.resource_type != "interactive" and obj.practice_quiz not in ({}, None):
        raise ValueError("Practice quiz content is only supported for interactive resources.")
    if obj.origin == "external" and obj.resource_type != "external_link":
        raise ValueError("External-origin content must be an external_link; do not copy third-party content into Marian.")
    if obj.origin == "external" and obj.body.strip():
        raise ValueError("External-origin resources may link to the source but may not copy its content into Marian.")
    frameworks = _relationship_ids(data["framework_ids"], LearningFramework, "framework_ids") if "framework_ids" in data else None
    topics = _relationship_ids(data["topic_ids"], LearningTopic, "topic_ids") if "topic_ids" in data else None
    return frameworks, topics


def _set_path_fields(obj, data):
    unknown = set(data) - PATH_INPUTS
    if unknown:
        raise ValueError("Unsupported path fields: " + ", ".join(sorted(unknown)))
    for name, maximum, required in (
        ("title", 240, True), ("description", 8000, False),
        ("source_name", 240, False), ("license_name", 160, False),
        ("attribution", 4000, False), ("rights_notes", 5000, False),
    ):
        if name in data:
            setattr(obj, name, _clean_text(data[name], name, maximum=maximum, required=required))
    if "objectives" in data:
        objectives = data["objectives"]
        if not isinstance(objectives, list) or len(objectives) > MAX_LIST:
            raise ValueError(f"objectives must be a list of at most {MAX_LIST} strings.")
        obj.objectives = [_clean_text(item, "objective", maximum=500, required=True) for item in objectives]
    if "language_code" in data:
        language = _normalize_language(data["language_code"])
        if language is None:
            raise ValueError("Use a valid language code, such as en or sw.")
        obj.language_code = language
    if "difficulty" in data:
        choices = {"", *(key for key, _ in LearningResource.DIFFICULTIES)}
        if not isinstance(data["difficulty"], str) or data["difficulty"] not in choices:
            raise ValueError("Invalid difficulty.")
        obj.difficulty = data["difficulty"]
    if "access_tier" in data:
        choices = {key for key, _ in LearningResource.ACCESS_TIERS}
        if not isinstance(data["access_tier"], str) or data["access_tier"] not in choices:
            raise ValueError("Invalid access_tier.")
        obj.access_tier = data["access_tier"]
    for field in ("age_min", "age_max"):
        if field in data:
            setattr(obj, field, _age_value(data[field], field))
    if "license_url" in data:
        obj.license_url = _https(data["license_url"], "license_url")
    frameworks = _relationship_ids(data["framework_ids"], LearningFramework, "framework_ids") if "framework_ids" in data else None
    topics = _relationship_ids(data["topic_ids"], LearningTopic, "topic_ids") if "topic_ids" in data else None
    return frameworks, topics


def _replace_path_items(path, values):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError("items must be a list of at most 100 path items.")
    expected = {"position", "item_type", "resource_id", "title", "instructions", "completion_rule"}
    prepared = []
    seen_positions = set()
    for value in values:
        if not isinstance(value, dict) or set(value) - expected:
            raise ValueError("Each path item must be an object containing only supported fields.")
        pos = value.get("position")
        item_type = value.get("item_type")
        if isinstance(pos, bool) or not isinstance(pos, int) or pos < 1 or pos in seen_positions:
            raise ValueError("Path item positions must be unique positive integers.")
        if not isinstance(item_type, str) or item_type not in {"resource", "activity", "project"}:
            raise ValueError("Invalid path item type.")
        rule = value.get("completion_rule", "view")
        if rule != "view":
            raise ValueError("Only the non-completing 'view' rule is available until verifiable completion rules are implemented.")
        resource = None
        resource_id = value.get("resource_id")
        if item_type == "resource":
            if isinstance(resource_id, bool) or not isinstance(resource_id, int) or resource_id <= 0:
                raise ValueError("Resource path items require a positive resource_id.")
            resource = LearningResource.objects.filter(pk=resource_id).first()
            if resource is None:
                raise ValueError("Referenced resource is unavailable.")
        elif resource_id is not None:
            raise ValueError("Only resource path items may specify resource_id.")
        title = _clean_text(value.get("title", ""), "item title", maximum=240, required=(item_type != "resource"))
        instructions = _clean_text(value.get("instructions", ""), "item instructions", maximum=4000)
        prepared.append((pos, item_type, resource, title, instructions, rule))
        seen_positions.add(pos)
    if seen_positions != set(range(1, len(prepared) + 1)):
        raise ValueError("Path item positions must be consecutive starting from 1.")
    LearningPathItem.objects.filter(path=path).delete()
    for pos, item_type, resource, title, instructions, rule in prepared:
        if resource is not None:
            if (
                resource.status != "published" or resource.published_at is None
                or resource.reviewed_by_id is None or resource.reviewed_at is None
                or resource.retired_at is not None
                or not (resource.scope == "public" or resource.school_id == path.school_id)
                or resource.language_code.lower() != path.language_code.lower()
            ):
                raise ValueError("Path items may use only active, reviewed published resources in the same language and an allowed scope.")
        LearningPathItem.objects.create(
            path=path, position=pos, item_type=item_type,
            resource=resource, title=title, instructions=instructions,
            completion_rule=rule,
        )


def _clean_model(obj):
    try:
        obj.full_clean(exclude=["frameworks", "topics", "reviewed_by"])
    except DjangoValidationError as exc:
        messages = exc.message_dict.values() if hasattr(exc, "message_dict") else [exc.messages]
        raise ValueError("Content metadata is invalid: " + "; ".join(str(item) for group in messages for item in group))


def _content_view(request, kind, obj):
    return Response(_resource_json(obj) if kind == "resource" else _path_json(obj))


def _save_content(request, kind, obj, data, creating):
    setter = _set_resource_fields if kind == "resource" else _set_path_fields
    relation_rows = setter(obj, data)
    if creating:
        obj.scope = "school"
        obj.school = _actor(request).school
        obj.author = request.user
        obj.status = "draft"
        obj.version = 1
        if kind == "path":
            obj.origin = "teacher"
    else:
        if obj.status not in {"draft", "changes_requested"}:
            return Response({"detail": "Only a draft or changes-requested version can be edited."}, status=409)
        obj.status = "draft"
        obj.version += 1
        obj.reviewed_by = None
        obj.reviewed_at = None
        if hasattr(obj, "license_verified_by"):
            obj.license_verified_by = None
            obj.license_verified_at = None
    if kind == "resource" and obj.origin == "external":
        if not obj.external_url:
            return Response({"detail": "External resources require an HTTPS source URL."}, status=400)
    _clean_model(obj)
    with transaction.atomic():
        obj.save()
        if relation_rows[0] is not None:
            obj.frameworks.set(relation_rows[0])
        if relation_rows[1] is not None:
            obj.topics.set(relation_rows[1])
        if kind == "path" and "items" in data:
            _replace_path_items(obj, data["items"])
        elif kind == "path" and creating:
            _replace_path_items(obj, [])
        _record_revision(obj, request.user)
        _audit(request, obj, f"{kind}_draft_created" if creating else f"{kind}_draft_updated", version=obj.version)
    return Response(_resource_json(obj) if kind == "resource" else _path_json(obj), status=201 if creating else 200)


def _collection(request, kind):
    if request.method == "GET":
        if set(request.query_params) - {"status", "limit"}:
            return Response({"detail": "Unsupported content filter."}, status=400)
        status = request.query_params.get("status")
        valid_states = {value for value, _ in LearningResource.STATES}
        if status and status not in valid_states:
            return Response({"detail": "Invalid content status."}, status=400)
        raw_limit = request.query_params.get("limit", "100")
        if not re.fullmatch(r"[1-9]\d{0,2}", raw_limit):
            return Response({"detail": "limit must be from 1 to 100."}, status=400)
        limit = min(int(raw_limit), 100)
        qs = _resource_queryset(request) if kind == "resource" else _path_queryset(request)
        if status:
            qs = qs.filter(status=status)
        rows = list(qs.order_by("-updated_at", "-id")[: limit + 1])
        serialize = _resource_json if kind == "resource" else _path_json
        return Response({"results": [serialize(obj) for obj in rows[:limit]], "truncated": len(rows) > limit})

    data, error = _body_object(request)
    if error:
        return error
    if not data:
        return Response({"detail": "Content fields are required."}, status=400)
    obj = LearningResource(scope="school", school=_actor(request).school) if kind == "resource" else LearningPath(scope="school", school=_actor(request).school, origin="teacher")
    try:
        return _save_content(request, kind, obj, data, creating=True)
    except (ValueError, DjangoValidationError) as exc:
        return Response({"detail": str(exc)}, status=400)


def _detail(request, kind, content_id):
    qs = _resource_queryset(request) if kind == "resource" else _path_queryset(request)
    obj = qs.filter(pk=content_id).first()
    if obj is None:
        return Response({"detail": "Learning content not found."}, status=404)
    if request.method == "GET":
        return _content_view(request, kind, obj)
    data, error = _body_object(request)
    if error:
        return error
    if not data:
        return Response({"detail": "Provide at least one content field to update."}, status=400)
    try:
        with transaction.atomic():
            locked = qs.select_for_update().filter(pk=content_id).first()
            if locked is None:
                return Response({"detail": "Learning content not found."}, status=404)
            return _save_content(request, kind, locked, data, creating=False)
    except (ValueError, DjangoValidationError) as exc:
        return Response({"detail": str(exc)}, status=400)


def _object_for_action(request, kind, content_id, *, reviewer=False):
    qs = LearningResource.objects.filter(pk=content_id) if kind == "resource" else LearningPath.objects.filter(pk=content_id)
    obj = qs.select_for_update().filter(scope="school", school_id=_actor(request).school_id).first()
    if obj is None or (not reviewer and not _can_manage(request, obj)):
        return None
    return obj


def _transition(request, kind, content_id, action):
    if request.query_params:
        return Response({"detail": "Content transitions do not accept query parameters."}, status=400)
    if action == "review" and not _is_admin(request):
        return Response({"detail": "Only a full school administrator may review content."}, status=403)
    if action == "publish" and not _is_admin(request):
        return Response({"detail": "Only a full school administrator may request publication."}, status=403)
    if action in {"submit", "publish", "archive", "retire"}:
        data, error = _body_object(request)
        if error:
            return error
        if data:
            return Response({"detail": "This transition does not accept client-supplied content or status fields."}, status=400)
    with transaction.atomic():
        obj = _object_for_action(request, kind, content_id, reviewer=(action in {"review", "publish"}))
        if obj is None:
            return Response({"detail": "Learning content not found."}, status=404)
        if action == "submit":
            if obj.status not in {"draft", "changes_requested"}:
                return Response({"detail": "Only a draft or changes-requested version can be submitted."}, status=409)
            error = _metadata_error(obj)
            if error:
                return Response({"detail": error}, status=400)
            if kind == "path":
                error = _path_items_error(obj)
                if error:
                    return Response({"detail": error}, status=400)
            obj.status = "in_review"
            obj.reviewed_by = None
            obj.reviewed_at = None
            save_fields = ["status", "reviewed_by", "reviewed_at", "updated_at"]
            if hasattr(obj, "license_verified_by"):
                obj.license_verified_by = None
                obj.license_verified_at = None
                save_fields += ["license_verified_by", "license_verified_at"]
            obj.save(update_fields=save_fields)
            _audit(request, obj, f"{kind}_submitted", version=obj.version)
            return _content_view(request, kind, obj)

        if action == "review":
            data, error = _body_object(request)
            if error:
                return error
            if set(data) - {"decision"}:
                return Response({"detail": "Review accepts only a decision; comments are not stored by this workflow."}, status=400)
            decision = data.get("decision")
            if not isinstance(decision, str) or decision not in {"approve", "request_changes"}:
                return Response({"detail": "decision must be approve or request_changes."}, status=400)
            if obj.status != "in_review":
                return Response({"detail": "Only submitted content can be reviewed."}, status=409)
            if obj.author_id == request.user.pk:
                return Response({"detail": "Authors cannot approve or review their own school content."}, status=403)
            error = _metadata_error(obj)
            if error:
                return Response({"detail": error}, status=400)
            if kind == "path":
                error = _path_items_error(obj)
                if error:
                    return Response({"detail": error}, status=400)
            obj.status = "approved" if decision == "approve" else "changes_requested"
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
            save_fields = ["status", "reviewed_by", "reviewed_at", "updated_at"]
            if decision == "approve" and hasattr(obj, "license_verified_by"):
                obj.license_verified_by = request.user
                obj.license_verified_at = obj.reviewed_at
                save_fields += ["license_verified_by", "license_verified_at"]
            obj.save(update_fields=save_fields)
            _audit(request, obj, f"{kind}_{'approved' if decision == 'approve' else 'changes_requested'}", version=obj.version)
            return _content_view(request, kind, obj)

        if action == "publish":
            # Hard-coded fail-closed policy gate. No code path mutates a record to
            # published until a separately approved policy change replaces it.
            _audit(request, obj, f"{kind}_publication_blocked", status=obj.status, version=obj.version)
            return Response({
                "code": "content_publication_policy_unapproved",
                "detail": "Publishing is disabled until licensing/rights, moderation/review, and shared-catalogue ownership policies are approved.",
            }, status=503)

        if action in {"archive", "retire"}:
            if obj.status == "published" and not _is_admin(request):
                return Response({"detail": "Only a full school administrator may retire published content."}, status=403)
            if obj.status == "archived":
                return _content_view(request, kind, obj)
            was_live = obj.status == "published"
            obj.status = "archived"
            fields = ["status", "updated_at"]
            if was_live and hasattr(obj, "retired_at"):
                obj.retired_at = timezone.now()
                fields.append("retired_at")
            obj.save(update_fields=fields)
            _audit(request, obj, f"{kind}_{'retired' if was_live else 'archived'}", prior_status="published" if was_live else "draft")
            return _content_view(request, kind, obj)

    return Response({"detail": "Unsupported content transition."}, status=400)


def _revisions(request, kind, content_id):
    qs = _resource_queryset(request) if kind == "resource" else _path_queryset(request)
    obj = qs.filter(pk=content_id).first()
    if obj is None:
        return Response({"detail": "Learning content not found."}, status=404)
    revisions = LearningContentRevision.objects.filter(
        resource=obj if kind == "resource" else None,
        path=obj if kind == "path" else None,
    )[:100]
    return Response({"results": [
        {"version": row.version, "snapshot": row.snapshot, "created_at": row.created_at,
         "created_by_id": row.created_by_id}
        for row in revisions
    ]})


def _translation_json(row):
    return {
        "id": row.pk, "resource_id": row.resource_id,
        "language_code": row.language_code, "title": row.title,
        "summary": row.summary, "body": row.body,
        "translation_source": row.translation_source,
        "translator_id": row.translator_id, "review_state": row.review_state,
        "reviewed_by_id": row.reviewed_by_id, "reviewed_at": row.reviewed_at,
    }


@api_view(["GET", "POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_resource_translations(request, resource_id):
    resource = _resource_queryset(request).filter(pk=resource_id).first()
    if resource is None:
        return Response({"detail": "Learning resource not found."}, status=404)
    if request.method == "GET":
        rows = resource.translations.select_related("translator", "reviewed_by").order_by("language_code")
        return Response({"results": [_translation_json(row) for row in rows[:100]]})
    data, error = _body_object(request)
    if error:
        return error
    allowed = {"language_code", "title", "summary", "body"}
    if set(data) - allowed:
        return Response({"detail": "Unsupported translation fields."}, status=400)
    language = _normalize_language(data.get("language_code"))
    if language is None or language == resource.language_code.lower():
        return Response({"detail": "A valid language different from the source resource is required."}, status=400)
    try:
        title = _clean_text(data.get("title"), "title", maximum=240, required=True)
        summary = _clean_text(data.get("summary", ""), "summary", maximum=4000)
        body = _clean_text(data.get("body", ""), "body", maximum=MAX_TEXT_BODY)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    with transaction.atomic():
        resource = _resource_queryset(request).select_for_update().filter(pk=resource_id).first()
        if resource is None:
            return Response({"detail": "Learning resource not found."}, status=404)
        row = resource.translations.select_for_update().filter(language_code=language).first()
        if row is None:
            row = LearningResourceTranslation(resource=resource, language_code=language)
        elif row.translator_id != request.user.pk and not _is_admin(request):
            return Response({"detail": "Translation not found."}, status=404)
        row.title, row.summary, row.body = title, summary, body
        row.translation_source = "human"
        row.translator = request.user
        row.review_state = "draft"
        row.reviewed_by = None
        row.reviewed_at = None
        try:
            row.full_clean()
        except DjangoValidationError as exc:
            return Response({"detail": "Translation metadata is invalid."}, status=400)
        row.save()
        resource.version += 1
        resource.save(update_fields=["version", "updated_at"])
        _record_revision(resource, request.user)
        _audit(request, resource, "resource_translation_draft_saved", version=resource.version, language=language)
    return Response(_translation_json(row), status=201)


@api_view(["POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def submit_resource_translation(request, resource_id, translation_id):
    with transaction.atomic():
        resource = LearningResource.objects.select_for_update().filter(
            pk=resource_id, scope="school", school_id=_actor(request).school_id,
        ).first()
        if resource is None:
            return Response({"detail": "Translation not found."}, status=404)
        row = resource.translations.select_for_update().filter(
            pk=translation_id, translator=request.user,
        ).first()
        if row is None:
            return Response({"detail": "Translation not found."}, status=404)
        if row.review_state != "draft":
            return Response({"detail": "Only a translation draft can be submitted."}, status=409)
        row.review_state = "in_review"
        row.save(update_fields=["review_state", "updated_at"])
        _audit(request, resource, "resource_translation_submitted", language=row.language_code)
    return Response(_translation_json(row))


@api_view(["POST"])
@permission_classes([FullSchoolContentReviewer, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def review_resource_translation(request, resource_id, translation_id):
    data, error = _body_object(request)
    if error:
        return error
    decision = data.get("decision")
    if set(data) - {"decision"} or not isinstance(decision, str) or decision not in {"approve", "request_changes"}:
        return Response({"detail": "decision must be approve or request_changes."}, status=400)
    with transaction.atomic():
        resource = LearningResource.objects.select_for_update().filter(
            pk=resource_id, scope="school", school_id=_actor(request).school_id,
        ).first()
        if resource is None:
            return Response({"detail": "Translation not found."}, status=404)
        row = resource.translations.select_for_update().select_related("translator").filter(
            pk=translation_id,
        ).first()
        if row is None:
            return Response({"detail": "Translation not found."}, status=404)
        if row.review_state != "in_review":
            return Response({"detail": "Only a submitted translation can be reviewed."}, status=409)
        if row.translator_id == request.user.pk:
            return Response({"detail": "Translators cannot approve their own translations."}, status=403)
        row.review_state = "approved" if decision == "approve" else "draft"
        row.reviewed_by = request.user
        row.reviewed_at = timezone.now()
        row.save(update_fields=["review_state", "reviewed_by", "reviewed_at", "updated_at"])
        resource.version += 1
        resource.save(update_fields=["version", "updated_at"])
        _record_revision(resource, request.user)
        _audit(request, resource, f"resource_translation_{'approved' if row.review_state == 'approved' else 'changes_requested'}", language=row.language_code, version=resource.version)
    return Response(_translation_json(row))


def _path_translation_json(row):
    return {
        "id": row.pk, "path_id": row.path_id, "language_code": row.language_code,
        "title": row.title, "description": row.description,
        "objectives": row.objectives, "translation_source": row.translation_source,
        "translator_id": row.translator_id, "review_state": row.review_state,
        "reviewed_by_id": row.reviewed_by_id, "reviewed_at": row.reviewed_at,
    }


@api_view(["GET", "POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_path_translations(request, path_id):
    path = _path_queryset(request).filter(pk=path_id).first()
    if path is None:
        return Response({"detail": "Learning path not found."}, status=404)
    if request.method == "GET":
        rows = path.translations.select_related("translator", "reviewed_by").order_by("language_code")[:100]
        return Response({"results": [_path_translation_json(row) for row in rows]})
    data, error = _body_object(request)
    if error:
        return error
    if set(data) - {"language_code", "title", "description", "objectives"}:
        return Response({"detail": "Unsupported path-translation fields."}, status=400)
    language = _normalize_language(data.get("language_code"))
    if language is None or language == path.language_code.lower():
        return Response({"detail": "A valid language different from the source path is required."}, status=400)
    try:
        title = _clean_text(data.get("title"), "title", maximum=240, required=True)
        description = _clean_text(data.get("description", ""), "description", maximum=8000)
        objectives = data.get("objectives", [])
        if not isinstance(objectives, list) or len(objectives) > MAX_LIST:
            raise ValueError(f"objectives must be a list of at most {MAX_LIST} strings.")
        objectives = [_clean_text(value, "objective", maximum=500, required=True) for value in objectives]
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    with transaction.atomic():
        path = _path_queryset(request).select_for_update().filter(pk=path_id).first()
        if path is None:
            return Response({"detail": "Learning path not found."}, status=404)
        row = path.translations.select_for_update().filter(language_code=language).first()
        if row is None:
            row = LearningPathTranslation(path=path, language_code=language)
        elif row.translator_id != request.user.pk and not _is_admin(request):
            return Response({"detail": "Translation not found."}, status=404)
        row.title = title
        row.description = description
        row.objectives = objectives
        row.translation_source = "human"
        row.translator = request.user
        row.review_state = "draft"
        row.reviewed_by = None
        row.reviewed_at = None
        try:
            row.full_clean()
        except DjangoValidationError:
            return Response({"detail": "Path-translation metadata is invalid."}, status=400)
        row.save()
        path.version += 1
        path.save(update_fields=["version", "updated_at"])
        _record_revision(path, request.user)
        _audit(request, path, "path_translation_draft_saved", language=language, version=path.version)
    return Response(_path_translation_json(row), status=201)


@api_view(["POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def submit_path_translation(request, path_id, translation_id):
    with transaction.atomic():
        path = LearningPath.objects.select_for_update().filter(
            pk=path_id, scope="school", school_id=_actor(request).school_id,
        ).first()
        if path is None:
            return Response({"detail": "Translation not found."}, status=404)
        row = path.translations.select_for_update().filter(
            pk=translation_id, translator=request.user,
        ).first()
        if row is None:
            return Response({"detail": "Translation not found."}, status=404)
        if row.review_state != "draft":
            return Response({"detail": "Only a translation draft can be submitted."}, status=409)
        row.review_state = "in_review"
        row.save(update_fields=["review_state", "updated_at"])
        _audit(request, path, "path_translation_submitted", language=row.language_code)
    return Response(_path_translation_json(row))


@api_view(["POST"])
@permission_classes([FullSchoolContentReviewer, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def review_path_translation(request, path_id, translation_id):
    data, error = _body_object(request)
    if error:
        return error
    decision = data.get("decision")
    if set(data) - {"decision"} or not isinstance(decision, str) or decision not in {"approve", "request_changes"}:
        return Response({"detail": "decision must be approve or request_changes."}, status=400)
    with transaction.atomic():
        path = LearningPath.objects.select_for_update().filter(
            pk=path_id, scope="school", school_id=_actor(request).school_id,
        ).first()
        if path is None:
            return Response({"detail": "Translation not found."}, status=404)
        row = path.translations.select_for_update().select_related("translator").filter(
            pk=translation_id,
        ).first()
        if row is None:
            return Response({"detail": "Translation not found."}, status=404)
        if row.review_state != "in_review":
            return Response({"detail": "Only a submitted translation can be reviewed."}, status=409)
        if row.translator_id == request.user.pk:
            return Response({"detail": "Translators cannot approve their own translations."}, status=403)
        row.review_state = "approved" if decision == "approve" else "draft"
        row.reviewed_by = request.user
        row.reviewed_at = timezone.now()
        row.save(update_fields=["review_state", "reviewed_by", "reviewed_at", "updated_at"])
        path.version += 1
        path.save(update_fields=["version", "updated_at"])
        _record_revision(path, request.user)
        _audit(request, path, f"path_translation_{'approved' if row.review_state == 'approved' else 'changes_requested'}", language=row.language_code, version=path.version)
    return Response(_path_translation_json(row))


@api_view(["GET", "POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_resources(request):
    return _collection(request, "resource")


@api_view(["GET", "PATCH"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_resource_detail(request, resource_id):
    return _detail(request, "resource", resource_id)


@api_view(["GET", "POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_paths(request):
    return _collection(request, "path")


@api_view(["GET", "PATCH"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_path_detail(request, path_id):
    return _detail(request, "path", path_id)


@api_view(["GET"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_resource_revisions(request, resource_id):
    return _revisions(request, "resource", resource_id)


@api_view(["GET"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_path_revisions(request, path_id):
    return _revisions(request, "path", path_id)


@api_view(["GET"])
@permission_classes([FullSchoolContentReviewer, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def studio_review_queue(request):
    resources = LearningResource.objects.filter(
        scope="school", school_id=_actor(request).school_id, status="in_review",
    ).select_related("author").order_by("created_at", "id")[:100]
    paths = LearningPath.objects.filter(
        scope="school", school_id=_actor(request).school_id, status="in_review",
    ).select_related("author").prefetch_related("items").order_by("created_at", "id")[:100]
    resource_translations = LearningResourceTranslation.objects.filter(
        resource__scope="school", resource__school_id=_actor(request).school_id,
        review_state="in_review",
    ).select_related("resource", "translator").order_by("created_at", "id")[:100]
    path_translations = LearningPathTranslation.objects.filter(
        path__scope="school", path__school_id=_actor(request).school_id,
        review_state="in_review",
    ).select_related("path", "translator").order_by("created_at", "id")[:100]
    resources = list(resources)
    paths = list(paths)
    resource_translations = list(resource_translations)
    path_translations = list(path_translations)
    LearningAuditEvent.objects.create(
        actor=request.user,
        school_id=_actor(request).school_id,
        scope="school",
        action="learning_content_review_queue_read",
        target_type="school",
        target_id=str(_actor(request).school_id),
        safe_details={
            "resources": len(resources), "paths": len(paths),
            "resource_translations": len(resource_translations),
            "path_translations": len(path_translations),
        },
    )
    return Response({
        "resources": [{"id": row.pk, "title": row.title, "author_id": row.author_id, "version": row.version} for row in resources],
        "paths": [{"id": row.pk, "title": row.title, "author_id": row.author_id, "version": row.version} for row in paths],
        "resource_translations": [
            {"id": row.pk, "resource_id": row.resource_id, "resource_title": row.resource.title,
             "language_code": row.language_code, "translator_id": row.translator_id}
            for row in resource_translations
        ],
        "path_translations": [
            {"id": row.pk, "path_id": row.path_id, "path_title": row.path.title,
             "language_code": row.language_code, "translator_id": row.translator_id}
            for row in path_translations
        ],
    })


@api_view(["POST"])
@permission_classes([FullSchoolContentReviewer, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def review_resource(request, resource_id):
    return _transition(request, "resource", resource_id, "review")


@api_view(["POST"])
@permission_classes([FullSchoolContentReviewer, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def review_path(request, path_id):
    return _transition(request, "path", path_id, "review")


@api_view(["POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def submit_resource(request, resource_id):
    return _transition(request, "resource", resource_id, "submit")


@api_view(["POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def submit_path(request, path_id):
    return _transition(request, "path", path_id, "submit")


@api_view(["POST"])
@permission_classes([FullSchoolContentReviewer, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def publish_resource(request, resource_id):
    return _transition(request, "resource", resource_id, "publish")


@api_view(["POST"])
@permission_classes([FullSchoolContentReviewer, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def publish_path(request, path_id):
    return _transition(request, "path", path_id, "publish")


@api_view(["POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def archive_resource(request, resource_id):
    return _transition(request, "resource", resource_id, "archive")


@api_view(["POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def archive_path(request, path_id):
    return _transition(request, "path", path_id, "archive")


@api_view(["POST"])
@permission_classes([SchoolContentAuthor, SchoolNotSuspended])
@throttle_classes([LearningContentThrottle])
def duplicate_resource(request, resource_id):
    src = _resource_queryset(request).filter(pk=resource_id).first()
    if src is None:
        return Response({"detail": "Not found."}, status=404)
    keep = ("title", "summary", "body", "practice_quiz", "resource_type",
            "origin", "external_url", "language_code", "difficulty",
            "age_min", "age_max", "access_tier", "source_name",
            "license_name", "license_url", "attribution", "rights_notes",
            "source_type", "license_expires_on")
    obj = LearningResource(**{f: getattr(src, f) for f in keep})
    obj.scope = "school"
    obj.school = _actor(request).school
    obj.author = request.user
    obj.status = "draft"
    obj.version = 1
    obj.parent = src
    _clean_model(obj)
    with transaction.atomic():
        obj.save()
        obj.frameworks.set(src.frameworks.all())
        obj.topics.set(src.topics.all())
        _record_revision(obj, request.user)
        _audit(request, obj, "resource_duplicated", version=obj.version, source_id=src.pk)
    return Response(_resource_json(obj), status=201)
