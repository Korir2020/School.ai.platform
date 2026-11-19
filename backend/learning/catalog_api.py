"""Read-only learner catalogue APIs with publication, scope and age gates.

No server-side URL fetching occurs. Private file delivery is a separate,
authorized API; storage keys are never serialized and file-only resources are
offered only when an active scanner-cleared attachment exists.
"""

import re

from django.db.models import Prefetch, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .models import (
    LearningFramework,
    LearningPath,
    LearningPathItem,
    LearningPrivateAsset,
    LearningPreference,
    LearningResource,
    LearningResourceTranslation,
    LearningTopic,
)
from .permissions import ActiveLearnerSelfService
from .subscription_policy import profile_can_access_tier
from .throttles import LearningCatalogThrottle


MAX_RESULTS = 200
MAX_SEARCH_LENGTH = 100
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")
RESOURCE_FORMATS = {value for value, _label in LearningResource.RESOURCE_TYPES}
DIFFICULTIES = {value for value, _label in LearningResource.DIFFICULTIES}
TOPIC_TYPES = {value for value, _label in LearningTopic.NODE_TYPES}


def _normalize_language(value):
    if not isinstance(value, str):
        return None
    value = value.strip().replace("_", "-").lower()
    if len(value) > 20 or not LANGUAGE_RE.fullmatch(value):
        return None
    return value


def _language_candidates(language):
    return list(dict.fromkeys((language, language.split("-")[0])))


def _requested_language(request, profile):
    if "lang" in request.query_params:
        language = _normalize_language(request.query_params.get("lang"))
        if language is None:
            return None, Response({"detail": "Use a valid language code, such as en or sw."}, status=400)
        return language, None
    try:
        preferred = profile.preferences.preferred_languages
    except LearningPreference.DoesNotExist:
        preferred = []
    if isinstance(preferred, list):
        for value in preferred:
            language = _normalize_language(value)
            if language:
                return language, None
    language = _normalize_language(profile.locale)
    return language or "en", None


def _allowed_query_keys(request, allowed):
    unsupported = set(request.query_params.keys()) - allowed
    if unsupported:
        return Response({"detail": "Unsupported catalogue filter."}, status=400)
    return None


def _parse_positive_id(value):
    if value is None or not re.fullmatch(r"[1-9]\d*", value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _age_for_profile(profile):
    """Return a safe exact/floor age for filtering; never serialize it."""
    if profile.account_kind == "public_learner":
        # Public profiles are adult-only; use the lowest adult age as a
        # conservative bound because exact DOB is not collected here.
        return 18
    if profile.account_kind != "school_student" or not profile.student_id:
        return None
    dob = profile.student.date_of_birth
    if dob is None:
        return None
    today = timezone.localdate()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 0 or age > 120:
        return None
    expected_band = "under_10" if age < 10 else "10_17" if age < 18 else "adult"
    # A changed/inconsistent DOB must not silently widen the age gate.
    if profile.age_band != expected_band:
        return None
    return age


def _age_q(age):
    if age is None:
        return Q(age_min__isnull=True, age_max__isnull=True)
    return (
        (Q(age_min__isnull=True) | Q(age_min__lte=age))
        & (Q(age_max__isnull=True) | Q(age_max__gte=age))
    )


def _age_allows(obj, age):
    if age is None:
        return obj.age_min is None and obj.age_max is None
    return (
        (obj.age_min is None or obj.age_min <= age)
        and (obj.age_max is None or obj.age_max >= age)
    )


def _scope_q(profile):
    if profile.account_kind == "public_learner":
        return Q(scope="public", school__isnull=True)
    return Q(scope="public", school__isnull=True) | Q(
        scope="school", school_id=profile.school_id,
    )


def _scope_allows(profile, obj):
    if obj.scope == "public":
        return obj.school_id is None
    return (
        profile.account_kind == "school_student"
        and profile.school_id is not None
        and obj.scope == "school"
        and obj.school_id == profile.school_id
    )


def _topic_queryset(profile, age):
    return LearningTopic.objects.filter(
        is_active=True,
    ).filter(
        Q(framework__isnull=True) | Q(framework__is_active=True),
    ).filter(
        Q(parent__isnull=True) | Q(parent__is_active=True),
    ).filter(_age_q(age)).select_related("framework", "parent")


def _translation_language_q(candidates, prefix=""):
    query = Q(pk__in=[])
    for language in candidates:
        query |= Q(**{f"{prefix}language_code__iexact": language})
    return query


def _approved_translations(candidates):
    return LearningResourceTranslation.objects.filter(
        review_state="approved",
        reviewed_by__isnull=False,
        reviewed_at__isnull=False,
    ).filter(_translation_language_q(candidates))


def _translation_prefetch(candidates, relation="translations"):
    return Prefetch(
        relation,
        queryset=_approved_translations(candidates),
        to_attr="catalog_translations",
    )


def _resource_queryset(profile, age, candidates):
    query = (
        LearningResource.objects.filter(
            status="published",
            published_at__isnull=False,
            reviewed_by__isnull=False,
            reviewed_at__isnull=False,
            retired_at__isnull=True,
        )
        .filter(_scope_q(profile))
        .filter(_age_q(age))
        .filter(
            (Q(origin="marian") | ~Q(license_name="") | ~Q(rights_notes=""))
            & (Q(origin="marian") | Q(external_url__istartswith="https://"))
            & (~Q(resource_type="external_link") | Q(external_url__istartswith="https://"))
        )
        .filter(
            Q(language_code__iexact=candidates[0])
            | Q(language_code__iexact=candidates[-1])
            | (
                Q(translations__review_state="approved")
                & Q(translations__reviewed_by__isnull=False)
                & Q(translations__reviewed_at__isnull=False)
                & _translation_language_q(candidates, prefix="translations__")
            )
        )
        .distinct()
        .select_related("school")
        .prefetch_related(
            "topics__framework",
            "topics__parent",
            "topics__parent__framework",
            "frameworks",
            _translation_prefetch(candidates),
            Prefetch(
                "private_assets",
                queryset=LearningPrivateAsset.objects.exclude(scan_state="deleted").only(
                    "id", "resource_id", "content_type", "size_bytes", "scan_state",
                    "created_at", "scanned_at", "deleted_at",
                ),
                to_attr="catalog_assets",
            ),
        )
    )
    return query


def _localized_resource(resource, candidates):
    translations = getattr(resource, "catalog_translations", [])
    by_language = {item.language_code.lower(): item for item in translations}
    for candidate in candidates:
        translation = by_language.get(candidate)
        if translation is not None:
            return {
                "title": translation.title,
                "summary": translation.summary,
                "body": translation.body,
                "display_language": translation.language_code,
            }
    source_language = (resource.language_code or "").lower()
    if source_language in candidates:
        return {
            "title": resource.title,
            "summary": resource.summary,
            "body": resource.body,
            "display_language": resource.language_code,
        }
    return None


def _resource_is_visible(profile, resource, age, candidates):
    if (
        resource.status != "published"
        or resource.published_at is None
        or resource.reviewed_by_id is None
        or resource.reviewed_at is None
        or resource.retired_at is not None
        or not _scope_allows(profile, resource)
        or not _age_allows(resource, age)
        or not profile_can_access_tier(profile, resource.access_tier)
    ):
        return False
    if resource.origin == "external":
        if not (resource.license_name.strip() or resource.rights_notes.strip()):
            return False
        if not (resource.external_url or "").lower().startswith("https://"):
            return False
    if resource.external_url and not resource.external_url.lower().startswith("https://"):
        return False
    if resource.resource_type == "external_link" and not (resource.external_url or "").lower().startswith("https://"):
        return False
    localized = _localized_resource(resource, candidates)
    if localized is None:
        return False
    assets = getattr(resource, "catalog_assets", None)
    if assets is None:
        assets = list(resource.private_assets.exclude(scan_state="deleted"))
    has_clean_asset = any(
        asset.scan_state == "clean" and asset.deleted_at is None for asset in assets
    )
    if not strip_tags(localized["body"] or "").strip() and not (resource.external_url or "").lower().startswith("https://") and not has_clean_asset:
        return False
    return True


def _safe_topic(topic, age):
    return bool(
        topic
        and topic.is_active
        and (topic.framework_id is None or topic.framework.is_active)
        and (topic.parent_id is None or topic.parent.is_active)
        and _age_allows(topic, age)
    )


def _topic_json(topic, language, age):
    localized_names = topic.localized_names if isinstance(topic.localized_names, dict) else {}
    display_name = None
    for candidate in _language_candidates(language):
        if isinstance(localized_names.get(candidate), str) and localized_names[candidate].strip():
            display_name = localized_names[candidate]
            break
    framework = topic.framework if topic.framework_id and topic.framework.is_active else None
    return {
        "id": topic.pk,
        "code": topic.code,
        "name": strip_tags(display_name or topic.name),
        "canonical_name": strip_tags(topic.name),
        "localized_names": {
            key: strip_tags(value) for key, value in localized_names.items()
            if isinstance(key, str) and isinstance(value, str)
        },
        "description": strip_tags(topic.description),
        "node_type": topic.node_type,
        "parent_id": topic.parent_id if topic.parent_id and topic.parent.is_active else None,
        "framework": ({"code": framework.code, "name": framework.name, "version": framework.version} if framework else None),
        "age_min": topic.age_min,
        "age_max": topic.age_max,
    }


def _youtube_embed(resource_type, url):
    """Derive a nocookie embed link from a strict YouTube pattern. No fetching."""
    import re
    from urllib.parse import parse_qs, urlparse
    if resource_type != "video" or not url:
        return None
    try:
        p = urlparse(url.strip())
        host = (p.hostname or "").lower()
        port = p.port
    except ValueError:
        return None
    if p.scheme != "https" or port or p.username or p.password:
        return None
    parts = [x for x in p.path.split("/") if x]
    vid = None
    if host == "youtu.be":
        if len(parts) == 1:
            vid = parts[0]
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if parts == ["watch"]:
            v = parse_qs(p.query).get("v", [])
            if len(v) == 1:
                vid = v[0]
        elif len(parts) == 2 and parts[0] in ("shorts", "embed"):
            vid = parts[1]
    if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        return "https://www.youtube-nocookie.com/embed/" + vid
    return None


def _resource_json(resource, language, age, detail=False):
    candidates = _language_candidates(language)
    localized = _localized_resource(resource, candidates)
    topics = [
        topic for topic in resource.topics.all()
        if _safe_topic(topic, age)
    ]
    frameworks = [
        {"code": framework.code, "name": framework.name, "version": framework.version}
        for framework in resource.frameworks.all() if framework.is_active
    ]
    assets = getattr(resource, "catalog_assets", None)
    if assets is None:
        assets = list(resource.private_assets.exclude(scan_state="deleted"))
    clean_assets = [
        asset for asset in assets
        if asset.scan_state == "clean" and asset.deleted_at is None
    ]
    data = {
        "id": resource.pk,
        "title": strip_tags(localized["title"]),
        "summary": strip_tags(localized["summary"] or ""),
        "resource_type": resource.resource_type,
        "origin": resource.origin,
        "language_code": resource.language_code,
        "display_language": localized["display_language"],
        "difficulty": resource.difficulty,
        "access_tier": resource.access_tier,
        "topics": [{"id": item.pk, "code": item.code, "name": strip_tags(item.name)} for item in topics],
        "frameworks": frameworks,
        "private_assets": [
            {
                "id": asset.pk,
                "content_type": asset.content_type,
                "size_bytes": asset.size_bytes,
                "download_url": reverse(
                    "learning:catalog-resource-asset-download",
                    kwargs={"resource_id": resource.pk, "asset_id": asset.pk},
                ),
            }
            for asset in clean_assets
        ],
    }
    if detail:
        data.update({
            "body": strip_tags(localized["body"] or ""),
            "external_url": resource.external_url if resource.external_url else None,
            "embed_url": _youtube_embed(resource.resource_type, resource.external_url),
            "source_name": strip_tags(resource.source_name or ""),
            "license_name": strip_tags(resource.license_name or ""),
            "attribution": strip_tags(resource.attribution or ""),
            "version": resource.version,
            "published_at": resource.published_at,
            # Neither a storage key nor the original filename leaves the server.
            "private_asset_pending": bool(resource.storage_key) or any(
                asset.scan_state != "clean" for asset in assets
            ),
        })
    return data


def _validate_catalog_filters(request, allowed, language):
    error = _allowed_query_keys(request, allowed)
    if error:
        return None, error
    filters = {}
    if "q" in request.query_params:
        query = request.query_params.get("q", "").strip()
        if len(query) > MAX_SEARCH_LENGTH:
            return None, Response({"detail": f"Search text must be at most {MAX_SEARCH_LENGTH} characters."}, status=400)
        filters["q"] = query
    if "topic_id" in request.query_params:
        topic_id = _parse_positive_id(request.query_params.get("topic_id"))
        if topic_id is None:
            return None, Response({"detail": "topic_id must be a positive integer."}, status=400)
        filters["topic_id"] = topic_id
    if "framework" in request.query_params:
        code = request.query_params.get("framework", "").strip()
        framework = LearningFramework.objects.filter(code__iexact=code, is_active=True).first()
        if not code or framework is None:
            return None, Response({"detail": "Choose an active learning framework."}, status=400)
        filters["framework"] = framework
    if "difficulty" in request.query_params:
        difficulty = request.query_params.get("difficulty", "").strip().lower()
        if difficulty not in DIFFICULTIES:
            return None, Response({"detail": "Choose beginner, intermediate, or advanced."}, status=400)
        filters["difficulty"] = difficulty
    if "resource_type" in request.query_params:
        resource_format = request.query_params.get("resource_type", "").strip().lower()
        if resource_format not in RESOURCE_FORMATS:
            return None, Response({"detail": "Choose a supported learning format."}, status=400)
        filters["resource_type"] = resource_format
    return filters, None


def _base_resource_filters(queryset, profile, age, candidates, filters):
    queryset = queryset.filter(_age_q(age))
    if "topic_id" in filters:
        topic = _topic_queryset(profile, age).filter(pk=filters["topic_id"]).first()
        if topic is None:
            return None, Response({"detail": "Topic is not available."}, status=400)
        queryset = queryset.filter(topics__pk=topic.pk)
    if "framework" in filters:
        queryset = queryset.filter(frameworks=filters["framework"])
    if "difficulty" in filters:
        queryset = queryset.filter(difficulty=filters["difficulty"])
    if "resource_type" in filters:
        queryset = queryset.filter(resource_type=filters["resource_type"])
    if filters.get("q"):
        text = filters["q"]
        translation_search = Q(
            translations__review_state="approved",
            translations__reviewed_by__isnull=False,
            translations__reviewed_at__isnull=False,
        ) & _translation_language_q(candidates, prefix="translations__") & (
            Q(translations__title__icontains=text)
            | Q(translations__summary__icontains=text)
        )
        queryset = queryset.filter(
            Q(title__icontains=text) | Q(summary__icontains=text) | translation_search,
        )
    return queryset.filter(_scope_q(profile)).filter(
        Q(language_code__iexact=candidates[0])
        | Q(language_code__iexact=candidates[-1])
        | (
            Q(translations__review_state="approved")
            & Q(translations__reviewed_by__isnull=False)
            & Q(translations__reviewed_at__isnull=False)
            & _translation_language_q(candidates, prefix="translations__")
        )
    ).distinct(), None


def _path_queryset(profile, age, candidates):
    item_translations = _approved_translations(candidates)
    item_queryset = LearningPathItem.objects.select_related("resource").prefetch_related(
        Prefetch("resource__translations", queryset=item_translations, to_attr="catalog_translations"),
        "resource__topics__framework",
        "resource__frameworks",
    )
    language_query = Q(pk__in=[])
    for language in candidates:
        language_query |= Q(language_code__iexact=language)
    return (
        LearningPath.objects.filter(
            status="published",
            published_at__isnull=False,
            reviewed_by__isnull=False,
            reviewed_at__isnull=False,
        )
        .filter(_scope_q(profile))
        .filter(_age_q(age))
        .filter(language_query)
        .select_related("school")
        .prefetch_related("topics__framework", "frameworks", Prefetch("items", queryset=item_queryset, to_attr="catalog_items"))
        .distinct()
    )


def _path_is_visible(profile, path, age, candidates):
    if (
        path.status != "published"
        or path.published_at is None
        or path.reviewed_by_id is None
        or path.reviewed_at is None
        or not _scope_allows(profile, path)
        or not _age_allows(path, age)
        or not profile_can_access_tier(profile, path.access_tier)
        or (path.language_code or "").lower() not in candidates
    ):
        return False
    items = getattr(path, "catalog_items", None)
    if items is None:
        items = list(path.items.select_related("resource").all())
    for item in items:
        if item.resource_id and not _resource_is_visible(profile, item.resource, age, candidates):
            return False
        if item.item_type == "resource" and not item.resource_id:
            return False
    return True


def _path_json(path, profile, language, age, detail=False):
    candidates = _language_candidates(language)
    topics = [topic for topic in path.topics.all() if _safe_topic(topic, age)]
    frameworks = [
        {"code": item.code, "name": item.name, "version": item.version}
        for item in path.frameworks.all() if item.is_active
    ]
    items = getattr(path, "catalog_items", None)
    if items is None:
        items = list(path.items.select_related("resource").all())
    data = {
        "id": path.pk,
        "title": strip_tags(path.title),
        "description": strip_tags(path.description or ""),
        "objectives": [strip_tags(item) for item in path.objectives[:50] if isinstance(item, str)] if isinstance(path.objectives, list) else [],
        "language_code": path.language_code,
        "difficulty": path.difficulty,
        "access_tier": path.access_tier,
        "origin": path.origin,
        "topics": [{"id": item.pk, "code": item.code, "name": strip_tags(item.name)} for item in topics],
        "frameworks": frameworks,
        "item_count": len(items),
        "version": path.version,
    }
    if detail:
        serialized_items = []
        for item in items:
            resource = item.resource if item.resource_id else None
            resource_data = _resource_json(resource, language, age) if resource else None
            serialized_items.append({
                "id": item.pk,
                "position": item.position,
                "item_type": item.item_type,
                "title": strip_tags(item.title or (resource_data["title"] if resource_data else "")),
                "instructions": strip_tags(item.instructions or ""),
                "completion_rule": item.completion_rule,
                "resource": ({"id": resource_data["id"], "title": resource_data["title"], "resource_type": resource_data["resource_type"], "display_language": resource_data["display_language"]} if resource_data else None),
            })
        data["items"] = serialized_items
        data["published_at"] = path.published_at
    return data


def _visible_rows(queryset, visible, limit=MAX_RESULTS):
    """Collect up to limit+1 visible rows, scanning past hidden candidates."""
    output = []
    offset = 0
    batch_size = limit + 1
    while len(output) <= limit:
        batch = list(queryset[offset:offset + batch_size])
        if not batch:
            break
        for item in batch:
            if visible(item):
                output.append(item)
                if len(output) > limit:
                    return output
        offset += len(batch)
    return output


def _topic_filters(request, profile, age):
    allowed = {"lang", "framework", "parent_id", "node_type"}
    error = _allowed_query_keys(request, allowed)
    if error:
        return None, error
    filters = {}
    if "framework" in request.query_params:
        code = request.query_params.get("framework", "").strip()
        framework = LearningFramework.objects.filter(code__iexact=code, is_active=True).first()
        if not code or framework is None:
            return None, Response({"detail": "Choose an active learning framework."}, status=400)
        filters["framework"] = framework
    if "parent_id" in request.query_params:
        parent_id = _parse_positive_id(request.query_params.get("parent_id"))
        parent = _topic_queryset(profile, age).filter(pk=parent_id).first() if parent_id else None
        if parent is None:
            return None, Response({"detail": "Parent topic is not available."}, status=400)
        filters["parent"] = parent
    if "node_type" in request.query_params:
        node_type = request.query_params.get("node_type", "").strip()
        if node_type not in TOPIC_TYPES:
            return None, Response({"detail": "Choose a supported topic type."}, status=400)
        filters["node_type"] = node_type
    return filters, None


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningCatalogThrottle])
def catalog_topics(request):
    profile = request.learning_profile
    language, error = _requested_language(request, profile)
    if error:
        return error
    age = _age_for_profile(profile)
    filters, error = _topic_filters(request, profile, age)
    if error:
        return error
    queryset = _topic_queryset(profile, age)
    if "framework" in filters:
        queryset = queryset.filter(framework=filters["framework"])
    if "parent" in filters:
        queryset = queryset.filter(parent=filters["parent"])
    if "node_type" in filters:
        queryset = queryset.filter(node_type=filters["node_type"])
    rows = list(queryset.order_by("sort_order", "name", "pk")[:MAX_RESULTS + 1])
    return Response({
        "results": [_topic_json(topic, language, age) for topic in rows[:MAX_RESULTS]],
        "truncated": len(rows) > MAX_RESULTS,
        "language": language,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningCatalogThrottle])
def catalog_resources(request):
    profile = request.learning_profile
    language, error = _requested_language(request, profile)
    if error:
        return error
    age = _age_for_profile(profile)
    candidates = _language_candidates(language)
    filters, error = _validate_catalog_filters(
        request, {"lang", "topic_id", "framework", "difficulty", "resource_type", "q"}, language,
    )
    if error:
        return error
    queryset, error = _base_resource_filters(
        _resource_queryset(profile, age, candidates), profile, age, candidates, filters,
    )
    if error:
        return error
    rows = _visible_rows(
        queryset.order_by("title", "pk"),
        lambda item: _resource_is_visible(profile, item, age, candidates),
    )
    return Response({
        "results": [_resource_json(item, language, age) for item in rows[:MAX_RESULTS]],
        "truncated": len(rows) > MAX_RESULTS,
        "language": language,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningCatalogThrottle])
def catalog_resource_detail(request, resource_id):
    profile = request.learning_profile
    error = _allowed_query_keys(request, {"lang"})
    if error:
        return error
    language, error = _requested_language(request, profile)
    if error:
        return error
    age = _age_for_profile(profile)
    candidates = _language_candidates(language)
    resource = _resource_queryset(profile, age, candidates).filter(pk=resource_id).first()
    if resource is None or not _resource_is_visible(profile, resource, age, candidates):
        return Response({"detail": "Not found."}, status=404)
    return Response(_resource_json(resource, language, age, detail=True))


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningCatalogThrottle])
def catalog_paths(request):
    profile = request.learning_profile
    language, error = _requested_language(request, profile)
    if error:
        return error
    age = _age_for_profile(profile)
    candidates = _language_candidates(language)
    filters, error = _validate_catalog_filters(
        request, {"lang", "topic_id", "framework", "difficulty", "q"}, language,
    )
    if error:
        return error
    queryset = _path_queryset(profile, age, candidates)
    if "topic_id" in filters:
        topic = _topic_queryset(profile, age).filter(pk=filters["topic_id"]).first()
        if topic is None:
            return Response({"detail": "Topic is not available."}, status=400)
        queryset = queryset.filter(topics=topic)
    if "framework" in filters:
        queryset = queryset.filter(frameworks=filters["framework"])
    if "difficulty" in filters:
        queryset = queryset.filter(difficulty=filters["difficulty"])
    if filters.get("q"):
        queryset = queryset.filter(Q(title__icontains=filters["q"]) | Q(description__icontains=filters["q"]))
    queryset = queryset.distinct().order_by("title", "pk")
    rows = _visible_rows(
        queryset,
        lambda item: _path_is_visible(profile, item, age, candidates),
    )
    return Response({
        "results": [_path_json(item, profile, language, age) for item in rows[:MAX_RESULTS]],
        "truncated": len(rows) > MAX_RESULTS,
        "language": language,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningCatalogThrottle])
def catalog_path_detail(request, path_id):
    profile = request.learning_profile
    error = _allowed_query_keys(request, {"lang"})
    if error:
        return error
    language, error = _requested_language(request, profile)
    if error:
        return error
    age = _age_for_profile(profile)
    candidates = _language_candidates(language)
    path = _path_queryset(profile, age, candidates).filter(pk=path_id).first()
    if path is None or not _path_is_visible(profile, path, age, candidates):
        return Response({"detail": "Not found."}, status=404)
    return Response(_path_json(path, profile, language, age, detail=True))
