"""Activity 18–19 APIs: learner-owned motivation and bounded offline learning."""
import re
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended
from schools.models import SchoolAdminProfile

from .catalog_api import (
    _age_for_profile, _language_candidates, _path_is_visible, _path_queryset,
    _requested_language, _resource_is_visible, _resource_queryset,
)
from .models import (
    LearningActivityEvent, LearningGoal, LearningMotivationSettings,
    LearningOfflineOperation, LearningOfflinePackage, LearningPathItem,
)
from .permissions import ActiveLearnerSelfService, FullSchoolLearningAdmin
from .throttles import LearningActivityThrottle

OFFLINE_MAX_DAYS = 7
MAX_OFFLINE_ITEMS = 20
MAX_OFFLINE_BYTES = 250000
ALLOWED_OFFLINE_EVENTS = {"started", "progress", "feedback"}


def _json(request):
    if not isinstance(request.data, dict):
        return None, Response({"detail": "Send a JSON object."}, status=400)
    return request.data, None


def _streak_days(events):
    days = sorted({event.occurred_at.date() for event in events}, reverse=True)
    if not days:
        return 0
    today = timezone.localdate()
    if days[0] not in {today, today - timedelta(days=1)}:
        return 0
    streak = 1
    for previous, current in zip(days, days[1:]):
        if previous - current != timedelta(days=1):
            break
        streak += 1
    return streak


def _motivation_payload(profile):
    settings, _ = LearningMotivationSettings.objects.get_or_create(profile=profile)
    events = list(LearningActivityEvent.objects.filter(profile=profile).only("event_type", "occurred_at"))
    starts = sum(item.event_type == "started" for item in events)
    checkins = sum(item.event_type in {"progress", "feedback"} for item in events)
    completed_goals = LearningGoal.objects.filter(profile=profile, state="completed").count()
    streak = _streak_days(events)
    milestones = [
        {"code": "first_start", "label": "First learning step", "earned": starts >= 1, "progress": min(starts, 1), "target": 1},
        {"code": "five_checkins", "label": "Five thoughtful check-ins", "earned": checkins >= 5, "progress": min(checkins, 5), "target": 5},
        {"code": "goal_complete", "label": "A goal completed", "earned": completed_goals >= 1, "progress": min(completed_goals, 1), "target": 1},
        {"code": "three_day_streak", "label": "Three-day learning rhythm", "earned": streak >= 3, "progress": min(streak, 3), "target": 3},
    ]
    challenges = [
        {"code": "gentle_three_day", "label": "Optional: learn on three different days", "progress": min(streak, 3), "target": 3, "completed": streak >= 3},
        {"code": "reflect_twice", "label": "Optional: record two self-reflections", "progress": min(checkins, 2), "target": 2, "completed": checkins >= 2},
    ]
    return {"enabled": settings.enabled, "streak_days": streak, "milestones": milestones, "challenges": challenges,
            "counts": {"starts": starts, "checkins": checkins, "completed_goals": completed_goals},
            "principles": ["No public rankings", "No rewards for clicks or time", "You can turn motivation features off"]}


@api_view(["GET", "PATCH"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
@throttle_classes([LearningActivityThrottle])
def learner_motivation(request):
    profile = request.learning_profile
    if request.method == "GET":
        return Response(_motivation_payload(profile))
    data, error = _json(request)
    if error:
        return error
    if set(data) != {"enabled"} or not isinstance(data["enabled"], bool):
        return Response({"detail": "Only the boolean enabled preference can be changed."}, status=400)
    settings, _ = LearningMotivationSettings.objects.get_or_create(profile=profile)
    settings.enabled = data["enabled"]
    settings.save(update_fields=["enabled", "updated_at"])
    return Response(_motivation_payload(profile))


@api_view(["GET"])
@permission_classes([FullSchoolLearningAdmin])
def school_learning_analytics(request):
    admin = request.learning_school_admin
    since = timezone.now() - timedelta(days=30)
    qs = LearningActivityEvent.objects.filter(profile__school_id=admin.school_id, occurred_at__gte=since)
    counts = {row["event_type"]: row["count"] for row in qs.values("event_type").annotate(count=Count("id"))}
    active_learners = qs.values("profile_id").distinct().count()
    return Response({"window_days": 30, "retention_days": 30, "scope": "school_aggregate", "school_id": admin.school_id,
                     "active_learners": active_learners, "events": counts,
                     "access_note": "Aggregated minimum-necessary learning usage only; no learner roster, marks, reports, or public-learner records."})


def _manifest_for(profile, resource_ids, path_ids, language):
    age = _age_for_profile(profile)
    candidates = _language_candidates(language)
    resources = []
    for resource in _resource_queryset(profile, age, candidates).filter(pk__in=resource_ids)[:MAX_OFFLINE_ITEMS]:
        if _resource_is_visible(profile, resource, age, candidates):
            resources.append({"id": resource.pk, "type": "resource", "title": resource.title, "summary": resource.summary,
                              "body": resource.body, "resource_type": resource.resource_type, "language_code": resource.language_code,
                              "topics": [{"id": t.pk, "name": t.name} for t in resource.topics.all()]})
    paths = []
    for path in _path_queryset(profile, age, candidates).filter(pk__in=path_ids)[:MAX_OFFLINE_ITEMS]:
        if not _path_is_visible(profile, path, age, candidates):
            continue
        items = []
        for item in path.catalog_items:
            item_data = {"id": item.pk, "position": item.position, "title": item.title, "instructions": item.instructions, "completion_rule": item.completion_rule}
            if item.resource_id:
                item_data["resource_id"] = item.resource_id
            items.append(item_data)
        paths.append({"id": path.pk, "type": "path", "title": path.title, "description": path.description,
                      "language_code": path.language_code, "version": path.version, "items": items})
    return {"language": language, "issued_for": profile.account_kind, "resources": resources, "paths": paths}


def _package_or_error(request, profile):
    package_id = request.data.get("package_id")
    device_id = str(request.data.get("device_id", ""))[:128]
    try:
        package_uuid = uuid.UUID(str(package_id))
    except (TypeError, ValueError, AttributeError):
        return None, Response({"detail": "A valid package_id is required."}, status=400)
    package = LearningOfflinePackage.objects.filter(package_id=package_uuid, profile=profile, device_id=device_id).first()
    if not package:
        return None, Response({"detail": "Offline package not found for this learner and device."}, status=404)
    if package.revoked_at or package.expires_at <= timezone.now():
        return None, Response({"code": "offline_package_unavailable", "detail": "This offline package has expired or been revoked."}, status=410)
    return package, None


@api_view(["GET", "POST"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
@throttle_classes([LearningActivityThrottle])
def offline_learning_packages(request):
    profile = request.learning_profile
    if request.method == "GET":
        rows = LearningOfflinePackage.objects.filter(profile=profile).order_by("-issued_at")[:10]
        return Response({"results": [{"package_id": str(row.package_id), "issued_at": row.issued_at, "expires_at": row.expires_at,
                                      "revoked": bool(row.revoked_at), "item_count": len(row.manifest.get("resources", [])) + len(row.manifest.get("paths", [])),
                                      "last_sync_at": row.last_sync_at} for row in rows]})
    data, error = _json(request)
    if error:
        return error
    allowed = {"device_id", "resource_ids", "path_ids", "lang"}
    if set(data) - allowed:
        return Response({"detail": "Unsupported offline package fields."}, status=400)
    device_id = str(data.get("device_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9._:-]{12,128}", device_id):
        return Response({"detail": "device_id must be an opaque device identifier of 12–128 characters."}, status=400)
    resource_ids = data.get("resource_ids", [])
    path_ids = data.get("path_ids", [])
    if not all(isinstance(value, int) and value > 0 for value in [*resource_ids, *path_ids]) or len(resource_ids) + len(path_ids) > MAX_OFFLINE_ITEMS:
        return Response({"detail": "Choose at most 20 valid resources or paths."}, status=400)
    language, error = _requested_language(request, profile)
    if error is not None:
        return error
    manifest = _manifest_for(profile, resource_ids, path_ids, language)
    if len(str(manifest).encode("utf-8")) > MAX_OFFLINE_BYTES:
        return Response({"detail": "This offline package is too large. Choose fewer items."}, status=413)
    now = timezone.now()
    package = LearningOfflinePackage.objects.create(profile=profile, device_id=device_id, manifest=manifest, expires_at=now + timedelta(days=OFFLINE_MAX_DAYS))
    return Response({"package_id": str(package.package_id), "device_id": device_id, "issued_at": package.issued_at, "expires_at": package.expires_at,
                     "manifest": manifest, "encryption": {"required": True, "algorithm": "AES-GCM", "storage": "encrypted IndexedDB"}}, status=201)


@api_view(["POST"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
@throttle_classes([LearningActivityThrottle])
def offline_learning_sync(request):
    data, error = _json(request)
    if error:
        return error
    package, error = _package_or_error(request, request.learning_profile)
    if error:
        return error
    operations = data.get("operations")
    if not isinstance(operations, list) or len(operations) > 50:
        return Response({"detail": "operations must be a list of at most 50 items."}, status=400)
    manifest_ids = {("resource", int(row["id"])) for row in package.manifest.get("resources", [])} | {("path", int(row["id"])) for row in package.manifest.get("paths", [])}
    results = []
    with transaction.atomic():
        for raw in operations:
            try:
                operation_id = uuid.UUID(str(raw.get("operation_id")))
            except (TypeError, ValueError, AttributeError):
                results.append({"operation_id": raw.get("operation_id"), "state": "conflict", "code": "invalid_operation_id"}); continue
            event_type, item_type, item_id = raw.get("event_type"), raw.get("item_type"), raw.get("item_id")
            payload = raw.get("details", {})
            existing = LearningOfflineOperation.objects.filter(package=package, operation_id=operation_id).first()
            if existing:
                results.append({"operation_id": str(operation_id), "state": existing.state, "code": existing.conflict_code}); continue
            valid = event_type in ALLOWED_OFFLINE_EVENTS and item_type in {"resource", "path"} and isinstance(item_id, int) and (item_type, item_id) in manifest_ids and isinstance(payload, dict)
            state, code = ("synced", "") if valid else ("conflict", "item_not_in_package_or_invalid_event")
            LearningOfflineOperation.objects.create(package=package, operation_id=operation_id, event_type=str(event_type)[:12], payload=raw, state=state, conflict_code=code, synced_at=timezone.now() if valid else None)
            if valid:
                # A package event is a receipt; the ordinary online activity API remains authoritative.
                results.append({"operation_id": str(operation_id), "state": "synced"})
            else:
                results.append({"operation_id": str(operation_id), "state": "conflict", "code": code})
        package.last_sync_at = timezone.now(); package.save(update_fields=["last_sync_at"])
    return Response({"package_id": str(package.package_id), "results": results, "synced": sum(item["state"] == "synced" for item in results), "conflicts": sum(item["state"] == "conflict" for item in results)})


@api_view(["POST"])
@permission_classes([ActiveLearnerSelfService, SchoolNotSuspended])
def offline_learning_revoke(request, package_id):
    package = LearningOfflinePackage.objects.filter(profile=request.learning_profile, package_id=package_id, revoked_at__isnull=True).first()
    if not package:
        return Response({"detail": "Offline package not found."}, status=404)
    package.revoked_at = timezone.now(); package.save(update_fields=["revoked_at"])
    return Response({"package_id": str(package.package_id), "revoked": True})
