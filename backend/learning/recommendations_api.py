"""Deterministic learner recommendations from explicit, permitted learning signals.

This module never imports or queries Marian examination, marks, attendance,
financial, report-card, or risk data. Recommendations are bounded, learner-owned,
explainable, and revalidated against the live catalogue before storage and display.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .catalog_api import (
    _age_for_profile,
    _language_candidates,
    _normalize_language,
    _localized_resource,
    _path_is_visible,
    _path_queryset,
    _requested_language,
    _resource_is_visible,
    _resource_queryset,
    _safe_topic,
    _topic_queryset,
)
from .models import (
    LearningActivityEvent,
    LearningAuditEvent,
    LearningGoal,
    LearningPathItem,
    LearningPreference,
    LearningProfile,
    LearningRecommendation,
)
from .permissions import ActiveLearnerSelfService
from .subscription_policy import profile_can_access_tier
from .throttles import LearningRecommendationThrottle

ALGORITHM_VERSION = "rules-v1"
REASON_CODE = "personalized_rules"
MAX_RESOURCE_CANDIDATES = 160
MAX_PATH_CANDIDATES = 80
MAX_RECENT_EVENTS = 80
MAX_RECOMMENDATIONS = 8
ACTIVITY_LOOKBACK_DAYS = 90
RECOMMENDATION_LIFETIME_DAYS = 30

SIGNAL_WEIGHTS = {
    "interest_match": 50,
    "goal_path_match": 45,
    "goal_topic_match": 40,
    "recent_topic_activity": 18,
    "format_match": 12,
    "difficulty_match": 10,
    "language_match": 8,
    "catalog_starter": 1,
}
SIGNAL_ORDER = tuple(SIGNAL_WEIGHTS)
SIGNAL_COPY = {
    "en": {
        "interest_match": "matches topics you chose",
        "goal_path_match": "supports a learning goal you set",
        "goal_topic_match": "connects to a topic in an active learning goal",
        "recent_topic_activity": "builds on topics you recently explored",
        "format_match": "fits a format you prefer",
        "difficulty_match": "matches your preferred difficulty",
        "language_match": "is available in a language you prefer",
        "catalog_starter": "is a starting point from the approved learning catalogue",
    },
    "sw": {
        "interest_match": "inaendana na mada ulizochagua",
        "goal_path_match": "inaunga mkono lengo la kujifunza uliloweka",
        "goal_topic_match": "inahusiana na mada ya lengo lako linaloendelea",
        "recent_topic_activity": "inaendeleza mada ulizojifunza hivi karibuni",
        "format_match": "inaendana na aina ya nyenzo unayopendelea",
        "difficulty_match": "inaendana na kiwango cha ugumu unachopendelea",
        "language_match": "inapatikana katika lugha unayopendelea",
        "catalog_starter": "ni mwanzo mzuri kutoka kwenye katalogi ya kujifunza iliyoidhinishwa",
    },
}


def explanation_for(signals, language):
    """Return a short, human-readable explanation from allowlisted reason codes."""
    base_language = (language or "en").lower().split("-")[0]
    copy = SIGNAL_COPY.get(base_language, SIGNAL_COPY["en"])
    ordered = [signal for signal in SIGNAL_ORDER if signal in set(signals)]
    if not ordered:
        ordered = ["catalog_starter"]
    phrases = [copy[signal] for signal in ordered]
    if len(phrases) == 1:
        return phrases[0][:500]
    conjunction = " and " if base_language != "sw" else " na "
    return (", ".join(phrases[:-1]) + conjunction + phrases[-1])[:500]


def safe_source_signals(reason_code, signals):
    """Filter stored JSON to the small public allowlist for each recommendation kind."""
    values = {value for value in signals if isinstance(value, str)} if isinstance(signals, list) else set()
    if reason_code == REASON_CODE:
        return [signal for signal in SIGNAL_ORDER if signal in values]
    if reason_code == "teacher_selected" and "teacher_curated" in values:
        return ["teacher_curated"]
    return []


def _safe_topics(item, age):
    return {
        topic.pk for topic in item.topics.all()
        if _safe_topic(topic, age)
    }


def _recent_topic_ids(profile, age, candidates):
    """Use only recent event target identities, never event details or duration."""
    since = timezone.now() - timedelta(days=ACTIVITY_LOOKBACK_DAYS)
    events = list(
        LearningActivityEvent.objects.filter(
            profile=profile,
            occurred_at__gte=since,
            event_type__in=["started", "progress", "feedback"],
        )
        .order_by("-occurred_at", "-pk")
        .only("id", "event_type", "resource_id", "path_item_id", "occurred_at")[:MAX_RECENT_EVENTS]
    )
    if not events:
        return set()

    item_ids = {event.path_item_id for event in events if event.path_item_id}
    path_items = {
        row[0]: (row[1], row[2])
        for row in LearningPathItem.objects.filter(pk__in=item_ids)
        .values_list("pk", "path_id", "resource_id")
    }
    resource_ids = {event.resource_id for event in events if event.resource_id}
    resource_ids.update(resource_id for _path_id, resource_id in path_items.values() if resource_id)
    path_ids = {path_id for path_id, _resource_id in path_items.values()}

    visible_resources = {}
    if resource_ids:
        for resource in _resource_queryset(profile, age, candidates).filter(pk__in=resource_ids):
            if _resource_is_visible(profile, resource, age, candidates):
                visible_resources[resource.pk] = resource

    visible_paths = {}
    if path_ids:
        for path in _path_queryset(profile, age, candidates).filter(pk__in=path_ids):
            if _path_is_visible(profile, path, age, candidates):
                visible_paths[path.pk] = path

    topics = set()
    for event in events:
        if event.resource_id and event.resource_id in visible_resources:
            topics.update(_safe_topics(visible_resources[event.resource_id], age))
        if event.path_item_id:
            path_id, resource_id = path_items.get(event.path_item_id, (None, None))
            path = visible_paths.get(path_id)
            if path is not None:
                topics.update(_safe_topics(path, age))
                if resource_id and resource_id in visible_resources:
                    topics.update(_safe_topics(visible_resources[resource_id], age))
    return topics


def _active_goal_signals(profile, age, candidates):
    goals = list(
        LearningGoal.objects.filter(profile=profile, state="active")
        .order_by("-updated_at", "-pk")[:100]
        .values_list("topic_id", "path_id")
    )
    topic_ids = {topic_id for topic_id, _path_id in goals if topic_id}
    topic_ids = set(
        _topic_queryset(profile, age).filter(pk__in=topic_ids).values_list("pk", flat=True)
    ) if topic_ids else set()
    path_ids = {path_id for _topic_id, path_id in goals if path_id}
    goal_paths = {}
    if path_ids:
        for path in _path_queryset(profile, age, candidates).filter(pk__in=path_ids):
            if _path_is_visible(profile, path, age, candidates):
                goal_paths[path.pk] = path
                topic_ids.update(_safe_topics(path, age))
                for item in getattr(path, "catalog_items", []):
                    if item.resource_id:
                        topic_ids.update(_safe_topics(item.resource, age))
    return topic_ids, set(goal_paths)


def _candidate_score(item, kind, age, preferred_topics, goal_topics,
                     goal_paths, recent_topics, formats, difficulty, languages,
                     language_candidates):
    topics = _safe_topics(item, age)
    signals = set()
    if topics & preferred_topics:
        signals.add("interest_match")
    if topics & goal_topics:
        signals.add("goal_topic_match")
    if kind == "path" and item.pk in goal_paths:
        signals.add("goal_path_match")
    if topics & recent_topics:
        signals.add("recent_topic_activity")
    if kind == "resource" and item.resource_type in formats:
        signals.add("format_match")
    if difficulty and item.difficulty == difficulty:
        signals.add("difficulty_match")

    localized = _localized_resource(item, language_candidates) if kind == "resource" else None
    language_value = _normalize_language(
        localized["display_language"] if localized else getattr(item, "language_code", "")
    )
    preferred_language_bases = {
        code.split("-")[0]
        for value in languages
        if (code := _normalize_language(value))
    }
    if language_value and language_value.split("-")[0] in preferred_language_bases:
        signals.add("language_match")
    if not signals:
        signals.add("catalog_starter")
    score = sum(SIGNAL_WEIGHTS[signal] for signal in signals)
    # Stable tie-breaking: the catalogue order is title then ID.
    return score, [signal for signal in SIGNAL_ORDER if signal in signals], topics


def _recommendation_key(kind, item_id):
    return (kind, int(item_id))


def _visible_candidates(profile, age, language, candidates, premium_allowed):
    tier_filter = ["free", "premium"] if premium_allowed else ["free"]
    output = []
    resources = _resource_queryset(profile, age, candidates).filter(
        access_tier__in=tier_filter,
    ).order_by("title", "pk")[:MAX_RESOURCE_CANDIDATES]
    for item in resources:
        if _resource_is_visible(profile, item, age, candidates):
            output.append(("resource", item))

    paths = _path_queryset(profile, age, candidates).filter(
        access_tier__in=tier_filter,
    ).order_by("title", "pk")[:MAX_PATH_CANDIDATES]
    for item in paths:
        if _path_is_visible(profile, item, age, candidates):
            output.append(("path", item))
    return output


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningRecommendationThrottle])
def generate_learner_recommendations(request):
    """Create/refresh a bounded set of explainable recommendations for the caller."""
    if set(request.query_params) - {"lang"}:
        return Response({"detail": "Only the lang filter is supported."}, status=400)
    if not isinstance(request.data, dict) or request.data:
        return Response({"detail": "Send an empty JSON object; recommendation inputs come from your saved learning preferences."}, status=400)

    profile_id = request.learning_profile.pk
    now = timezone.now()
    with transaction.atomic():
        # Serializes overlapping refreshes for this learner on production DBs.
        profile = LearningProfile.objects.select_for_update().select_related(
            "school", "student",
        ).get(pk=profile_id)
        try:
            preference = LearningPreference.objects.select_for_update().get(profile=profile)
        except LearningPreference.DoesNotExist:
            preference = None

        enabled = preference.recommendations_enabled if preference else True
        if not enabled:
            LearningAuditEvent.objects.create(
                actor=request.user, school_id=profile.school_id,
                scope="school" if profile.school_id else "public",
                action="learner_recommendations_generate",
                target_type="learning_profile", target_id=str(profile.pk),
                safe_details={"enabled": False, "generated": 0},
            )
            return Response({"enabled": False, "generated": 0, "detail": "Personalized recommendations are paused in your preferences."})

        language, error = _requested_language(request, profile)
        if error is not None:
            return error
        language = _normalize_language(language)
        if language is None:
            return Response({"detail": "Use a valid learning language, such as en or sw."}, status=400)
        candidates = _language_candidates(language)
        age = _age_for_profile(profile)
        if age is None:
            return Response({"detail": "Learning recommendations are unavailable until learner age eligibility is verified."}, status=403)

        preferred_topics = set()
        formats = set()
        difficulty = ""
        languages = []
        if preference:
            preferred_topics = set(
                preference.topics.filter(is_active=True)
                .values_list("pk", flat=True)
            )
            formats = {
                value for value in (preference.preferred_formats or [])
                if isinstance(value, str)
            }
            difficulty = preference.preferred_difficulty or ""
            languages = [
                value for value in (preference.preferred_languages or [])
                if isinstance(value, str) and _normalize_language(value)
            ]
        if not languages:
            languages = [profile.locale or language]

        goal_topics, goal_paths = _active_goal_signals(profile, age, candidates)
        recent_topics = _recent_topic_ids(profile, age, candidates)
        premium_allowed = profile_can_access_tier(profile, "premium")
        visible = _visible_candidates(profile, age, language, candidates, premium_allowed)

        ranked = []
        for kind, item in visible:
            score, signals, topic_ids = _candidate_score(
                item, kind, age, preferred_topics, goal_topics,
                goal_paths, recent_topics, formats, difficulty, languages, candidates,
            )
            ranked.append({
                "kind": kind, "item": item, "score": score,
                "signals": signals, "topic_ids": topic_ids,
            })
        ranked.sort(key=lambda row: (-row["score"], row["kind"], row["item"].title.casefold(), row["item"].pk))

        resource_ids = [row["item"].pk for row in ranked if row["kind"] == "resource"]
        path_ids = [row["item"].pk for row in ranked if row["kind"] == "path"]
        existing_rows = LearningRecommendation.objects.select_for_update().filter(profile=profile).filter(
            Q(resource_id__in=resource_ids) | Q(path_id__in=path_ids)
        ).order_by("-created_at", "-pk") if resource_ids or path_ids else LearningRecommendation.objects.none()
        existing_by_key = {}
        for row in existing_rows:
            key = _recommendation_key("resource" if row.resource_id else "path", row.resource_id or row.path_id)
            existing_by_key.setdefault(key, []).append(row)

        selected = []
        for candidate in ranked:
            item = candidate["item"]
            key = _recommendation_key(candidate["kind"], item.pk)
            rows = existing_by_key.get(key, [])
            # A learner dismissal applies to the item, so a different source
            # cannot immediately surface the same dismissed suggestion again.
            if any(row.state == "dismissed" for row in rows):
                continue
            if any(row.state in {"shown", "accepted"} and row.reason_code != REASON_CODE for row in rows):
                continue
            selected.append(candidate)
            if len(selected) >= MAX_RECOMMENDATIONS:
                break

        selected_keys = {_recommendation_key(row["kind"], row["item"].pk) for row in selected}
        stale_auto = LearningRecommendation.objects.select_for_update().filter(
            profile=profile, reason_code=REASON_CODE, state="shown",
        )
        for row in stale_auto:
            key = _recommendation_key("resource" if row.resource_id else "path", row.resource_id or row.path_id)
            if key not in selected_keys:
                row.state = "expired"
                row.responded_at = now
                row.save(update_fields=["state", "responded_at"])

        refreshed = 0
        created = 0
        # Reverse insertion order keeps the highest-ranked row newest in the inbox.
        for candidate in reversed(selected):
            item = candidate["item"]
            kind = candidate["kind"]
            key = _recommendation_key(kind, item.pk)
            rows = existing_by_key.get(key, [])
            auto = next((row for row in rows if row.reason_code == REASON_CODE and row.state in {"shown", "accepted", "expired"}), None)
            signals = candidate["signals"]
            explanation = explanation_for(signals, language)
            target = {"resource": item, "path": None} if kind == "resource" else {"resource": None, "path": item}
            if auto is None:
                LearningRecommendation.objects.create(
                    profile=profile,
                    reason_code=REASON_CODE,
                    explanation=explanation,
                    source_signals=signals,
                    algorithm_version=ALGORITHM_VERSION,
                    state="shown",
                    expires_at=now + timedelta(days=RECOMMENDATION_LIFETIME_DAYS),
                    **target,
                )
                created += 1
                continue
            auto.source_signals = signals
            auto.explanation = explanation
            auto.algorithm_version = ALGORITHM_VERSION
            auto.expires_at = now + timedelta(days=RECOMMENDATION_LIFETIME_DAYS)
            update_fields = ["source_signals", "explanation", "algorithm_version", "expires_at"]
            if auto.state == "expired":
                auto.state = "shown"
                auto.responded_at = None
                update_fields.extend(["state", "responded_at"])
            auto.save(update_fields=update_fields)
            refreshed += 1

    LearningRecommendation.objects.filter(
        profile_id=profile_id, reason_code=REASON_CODE,
        state__in=["shown", "accepted"], expires_at__lte=now,
    ).update(state="expired", responded_at=now)
    LearningAuditEvent.objects.create(
        actor=request.user, school_id=profile.school_id,
        scope="school" if profile.school_id else "public",
        action="learner_recommendations_generate",
        target_type="learning_profile", target_id=str(profile.pk),
        safe_details={
            "enabled": True,
            "generated": created,
            "refreshed": refreshed,
            "active": len(selected),
            "algorithm_version": ALGORITHM_VERSION,
        },
    )
    return Response({
        "enabled": True,
        "generated": created,
        "refreshed": refreshed,
        "active_personalized": len(selected),
        "algorithm_version": ALGORITHM_VERSION,
    })
