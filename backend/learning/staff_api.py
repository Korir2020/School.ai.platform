"""Teacher-facing learning discovery, assigned progress, and recommendations.

Every learner lookup is constrained by the teacher's active Marian assignments.
Only reviewed, published, free catalogue items may be recommended; this module
never reads marks, attendance, fees, raw AI prompts, or report-card records.
"""

from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import restrict_for_teacher
from api.suspension import SchoolNotSuspended
from schools.models import SchoolAdminProfile, Student, TeacherAssignment, TeacherProfile

from .accounts_api import _profile_summary
from .catalog_api import (
    MAX_RESULTS,
    _age_for_profile,
    _base_resource_filters,
    _language_candidates,
    _normalize_language,
    _path_is_visible,
    _path_json,
    _path_queryset,
    _resource_is_visible,
    _resource_json,
    _resource_queryset,
    _safe_topic,
    _topic_json,
    _topic_queryset,
    _validate_catalog_filters,
    _visible_rows,
)
from .models import (
    LearningAuditEvent,
    LearningPath,
    LearningPreference,
    LearningProfile,
    LearningRecommendation,
    LearningResource,
    LearningSchoolSettings,
)
from .recommendations_api import explanation_for, safe_source_signals
from .permissions import ActiveLearnerSelfService, TeacherLearningStudio, learner_profile_is_eligible
from .throttles import LearningCatalogThrottle, LearningProfileThrottle


def _settings(school_id):
    return LearningSchoolSettings.objects.filter(school_id=school_id).first()


def _age_allowed(profile, age):
    if profile.account_kind != "school_student":
        return True
    settings = _settings(profile.school_id)
    if settings is None:
        return True
    return bool(
        settings.learning_access_enabled
        and age is not None
        and settings.minimum_learner_age <= age <= settings.maximum_learner_age
    )


def _staff_catalog_profile(school_id):
    # Catalogue helpers only read account kind and school scope for free items.
    # Premium access remains unavailable to this staff-only discovery surface.
    return SimpleNamespace(account_kind="school_student", school_id=school_id, account_status="active")


def _teacher_assigned_students(teacher):
    stream_ids = TeacherAssignment.objects.filter(
        teacher=teacher, school_id=teacher.school_id,
    ).values_list("stream_id", flat=True)
    return restrict_for_teacher(
        teacher.user,
        Student.objects.filter(
            school_id=teacher.school_id,
            status="active",
            enrollment__is_active=True,
            enrollment__academic_year__is_active=True,
            enrollment__stream_id__in=stream_ids,
        ),
    ).distinct()


def _assigned_profile(request, student_id):
    teacher = request.learning_school_teacher
    student = _teacher_assigned_students(teacher).filter(pk=student_id).first()
    if student is None:
        return None, None
    profile = LearningProfile.objects.select_related("student", "school").filter(
        student_id=student.pk,
        school_id=teacher.school_id,
        account_kind="school_student",
    ).first()
    if profile is None or not learner_profile_is_eligible(profile):
        return student, None
    age = _age_for_profile(profile)
    if not _age_allowed(profile, age):
        return student, None
    return student, profile


def _audit(request, action, *, target_type="learning_workspace", target_id="", details=None):
    school_id = request.learning_school_teacher.school_id
    LearningAuditEvent.objects.create(
        actor=request.user,
        school_id=school_id,
        scope="school",
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        safe_details=details or {},
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningProfileThrottle])
def teacher_assigned_learners(request):
    """Return only assigned, eligible profiles and minimum progress summaries."""
    teacher = request.learning_school_teacher
    students = _teacher_assigned_students(teacher).order_by("last_name", "first_name", "pk")
    profiles = list(
        LearningProfile.objects.filter(
            school_id=teacher.school_id,
            account_kind="school_student",
            student_id__in=students.values("pk"),
        ).select_related("student").order_by("student__last_name", "student__first_name", "pk")[:201]
    )
    results = []
    for profile in profiles:
        age = _age_for_profile(profile)
        if not learner_profile_is_eligible(profile) or not _age_allowed(profile, age):
            continue
        summary = _profile_summary(profile)
        summary.pop("age_band", None)
        summary.pop("account_status", None)
        summary["student_id"] = profile.student_id
        summary["learner_name"] = f"{profile.student.first_name} {profile.student.last_name}".strip()
        results.append(summary)
        if len(results) == 200:
            break
    _audit(request, "teacher_assigned_learning_progress_list_read", details={"count": len(results)})
    return Response({"results": results, "truncated": len(profiles) > 200})


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningCatalogThrottle])
def teacher_catalog_topics(request):
    if set(request.query_params) - {"lang"}:
        return Response({"detail": "Unsupported catalogue filter."}, status=400)
    language = _normalize_language(request.query_params.get("lang", "en"))
    if language is None:
        return Response({"detail": "Use a valid language code, such as en or sw."}, status=400)
    topics = _topic_queryset(_staff_catalog_profile(request.learning_school_teacher.school_id), 18)
    rows = list(topics.order_by("sort_order", "name", "pk")[:MAX_RESULTS + 1])
    return Response({
        "results": [_topic_json(topic, language, 18) for topic in rows[:MAX_RESULTS]],
        "truncated": len(rows) > MAX_RESULTS,
        "language": language,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningCatalogThrottle])
def teacher_catalog_resources(request):
    language = _normalize_language(request.query_params.get("lang", "en"))
    if language is None:
        return Response({"detail": "Use a valid language code, such as en or sw."}, status=400)
    profile = _staff_catalog_profile(request.learning_school_teacher.school_id)
    candidates = _language_candidates(language)
    filters, error = _validate_catalog_filters(
        request, {"lang", "topic_id", "framework", "difficulty", "resource_type", "q"}, language,
    )
    if error:
        return error
    queryset, error = _base_resource_filters(
        _resource_queryset(profile, 18, candidates).filter(access_tier="free"),
        profile, 18, candidates, filters,
    )
    if error:
        return error
    rows = _visible_rows(
        queryset.order_by("title", "pk"),
        lambda item: item.access_tier == "free" and _resource_is_visible(profile, item, 18, candidates),
    )
    results = []
    for item in rows[:MAX_RESULTS]:
        result = _resource_json(item, language, 18)
        # Staff learning is intentionally text/catalogue only here; private asset
        # downloads continue through the learner's own authorization endpoints.
        result["private_assets"] = []
        results.append(result)
    return Response({"results": results, "truncated": len(rows) > MAX_RESULTS, "language": language})


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningCatalogThrottle])
def teacher_catalog_paths(request):
    language = _normalize_language(request.query_params.get("lang", "en"))
    if language is None:
        return Response({"detail": "Use a valid language code, such as en or sw."}, status=400)
    profile = _staff_catalog_profile(request.learning_school_teacher.school_id)
    candidates = _language_candidates(language)
    filters, error = _validate_catalog_filters(
        request, {"lang", "topic_id", "framework", "difficulty", "q"}, language,
    )
    if error:
        return error
    queryset = _path_queryset(profile, 18, candidates)
    if "topic_id" in filters:
        topic = _topic_queryset(profile, 18).filter(pk=filters["topic_id"]).first()
        if topic is None:
            return Response({"detail": "Topic is not available."}, status=400)
        queryset = queryset.filter(topics=topic)
    if "framework" in filters:
        queryset = queryset.filter(frameworks=filters["framework"])
    if "difficulty" in filters:
        queryset = queryset.filter(difficulty=filters["difficulty"])
    if filters.get("q"):
        queryset = queryset.filter(Q(title__icontains=filters["q"]) | Q(description__icontains=filters["q"]))
    rows = _visible_rows(
        queryset.distinct().order_by("title", "pk"),
        lambda item: item.access_tier == "free" and _path_is_visible(profile, item, 18, candidates),
    )
    return Response({
        "results": [_path_json(item, profile, language, 18) for item in rows[:MAX_RESULTS]],
        "truncated": len(rows) > MAX_RESULTS,
        "language": language,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningCatalogThrottle])
def teacher_catalog_resource_detail(request, resource_id):
    if set(request.query_params) - {"lang"}:
        return Response({"detail": "Unsupported catalogue filter."}, status=400)
    language = _normalize_language(request.query_params.get("lang", "en"))
    if language is None:
        return Response({"detail": "Use a valid language code, such as en or sw."}, status=400)
    profile = _staff_catalog_profile(request.learning_school_teacher.school_id)
    candidates = _language_candidates(language)
    resource = _resource_queryset(profile, 18, candidates).filter(
        pk=resource_id, access_tier="free",
    ).first()
    if resource is None or not _resource_is_visible(profile, resource, 18, candidates):
        return Response({"detail": "Not found."}, status=404)
    result = _resource_json(resource, language, 18, detail=True)
    result["private_assets"] = []
    _audit(request, "teacher_learning_resource_read", target_type="resource", target_id=resource.pk)
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningCatalogThrottle])
def teacher_catalog_path_detail(request, path_id):
    if set(request.query_params) - {"lang"}:
        return Response({"detail": "Unsupported catalogue filter."}, status=400)
    language = _normalize_language(request.query_params.get("lang", "en"))
    if language is None:
        return Response({"detail": "Use a valid language code, such as en or sw."}, status=400)
    profile = _staff_catalog_profile(request.learning_school_teacher.school_id)
    candidates = _language_candidates(language)
    path = _path_queryset(profile, 18, candidates).filter(pk=path_id, access_tier="free").first()
    if path is None or not _path_is_visible(profile, path, 18, candidates):
        return Response({"detail": "Not found."}, status=404)
    result = _path_json(path, profile, language, 18, detail=True)
    _audit(request, "teacher_learning_path_read", target_type="path", target_id=path.pk)
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningProfileThrottle])
def recommend_learning_item(request, student_id):
    if not isinstance(request.data, dict) or set(request.data) - {"resource_id", "path_id", "explanation"}:
        return Response({"detail": "Provide exactly one resource_id or path_id and an optional explanation."}, status=400)
    target_keys = [key for key in ("resource_id", "path_id") if key in request.data]
    if len(target_keys) != 1:
        return Response({"detail": "Provide exactly one resource_id or path_id."}, status=400)
    student, profile = _assigned_profile(request, student_id)
    if student is None or profile is None:
        return Response({"detail": "Assigned learner not found or not eligible for learning access."}, status=404)
    settings = _settings(profile.school_id)
    if settings and not settings.teacher_recommendations_enabled:
        return Response({"code": "teacher_recommendations_disabled", "detail": "School administrators have disabled teacher recommendations."}, status=403)

    explanation = request.data.get("explanation", "")
    if not isinstance(explanation, str) or len(explanation) > 500:
        return Response({"detail": "explanation must be text of at most 500 characters."}, status=400)
    explanation = strip_tags(explanation).strip()
    age = _age_for_profile(profile)
    if age is None:
        return Response({"detail": "The learner's age could not be verified."}, status=403)
    language = _normalize_language(profile.locale or "en") or "en"
    candidates = _language_candidates(language)

    key = target_keys[0]
    try:
        raw_id = request.data[key]
        if isinstance(raw_id, bool):
            raise ValueError
        target_id = int(raw_id)
        if target_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return Response({"detail": f"{key} must be a positive integer."}, status=400)

    target = None
    if key == "resource_id":
        target = _resource_queryset(profile, age, candidates).filter(
            pk=target_id, access_tier="free",
        ).first()
        if target is None or not _resource_is_visible(profile, target, age, candidates):
            return Response({"detail": "Only currently visible, reviewed, published free resources may be recommended."}, status=404)
        duplicate = LearningRecommendation.objects.filter(
            profile=profile, resource=target, state__in=["shown", "accepted"],
        ).exists()
        recommendation_kwargs = {"resource": target, "path": None}
        target_type = "resource"
    else:
        target = _path_queryset(profile, age, candidates).filter(
            pk=target_id, access_tier="free",
        ).first()
        if target is None or not _path_is_visible(profile, target, age, candidates):
            return Response({"detail": "Only currently visible, reviewed, published free learning paths may be recommended."}, status=404)
        duplicate = LearningRecommendation.objects.filter(
            profile=profile, path=target, state__in=["shown", "accepted"],
        ).exists()
        recommendation_kwargs = {"resource": None, "path": target}
        target_type = "path"
    if duplicate:
        return Response({"detail": "This item already has an active recommendation for this learner."}, status=409)

    with transaction.atomic():
        recommendation = LearningRecommendation.objects.create(
            profile=profile,
            reason_code="teacher_selected",
            explanation=explanation,
            source_signals=["teacher_curated"],
            algorithm_version="teacher-v1",
            state="shown",
            **recommendation_kwargs,
        )
        _audit(
            request, "teacher_learning_item_recommended",
            target_type=target_type, target_id=target.pk,
            details={"recommendation_id": recommendation.pk, "profile_id": profile.pk},
        )
    return Response({"id": recommendation.pk, "state": recommendation.state}, status=201)


def _visible_recommendation_item(profile, row, language, age):
    candidates = _language_candidates(language)
    if row.resource_id:
        resource = _resource_queryset(profile, age, candidates).filter(pk=row.resource_id).first()
        if resource is None or not _resource_is_visible(profile, resource, age, candidates):
            return None
        return {"type": "resource", "item": _resource_json(resource, language, age)}
    path = _path_queryset(profile, age, candidates).filter(pk=row.path_id).first()
    if path is None or not _path_is_visible(profile, path, age, candidates):
        return None
    return {"type": "path", "item": _path_json(path, profile, language, age)}


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningProfileThrottle])
def learner_recommendations(request):
    if set(request.query_params) - {"lang"}:
        return Response({"detail": "Unsupported recommendation filter."}, status=400)
    profile = request.learning_profile
    language = _normalize_language(request.query_params.get("lang", profile.locale or "en"))
    if language is None:
        return Response({"detail": "Use a valid language code, such as en or sw."}, status=400)
    age = _age_for_profile(profile)
    if not _age_allowed(profile, age):
        return Response({"code": "school_learning_access_disabled", "detail": "School learning access is unavailable for this account."}, status=403)
    now = timezone.now()
    LearningRecommendation.objects.filter(
        profile=profile, state__in=["shown", "accepted"], expires_at__lte=now,
    ).update(state="expired", responded_at=now)
    try:
        recommendations_enabled = profile.preferences.recommendations_enabled
    except LearningPreference.DoesNotExist:
        recommendations_enabled = True
    queryset = LearningRecommendation.objects.filter(
        profile=profile, state__in=["shown", "accepted"],
    )
    if not recommendations_enabled:
        queryset = queryset.exclude(reason_code="personalized_rules")
    rows = list(queryset.select_related("resource", "path").order_by("-created_at", "-pk")[:51])
    results = []
    for row in rows[:50]:
        if row.reason_code not in {"teacher_selected", "personalized_rules"}:
            if row.state == "shown":
                row.state = "expired"
                row.save(update_fields=["state"])
            continue
        visible = _visible_recommendation_item(profile, row, language, age)
        if visible is None:
            if row.state == "shown":
                row.state = "expired"
                row.save(update_fields=["state"])
            continue
        results.append({
            "id": row.pk,
            "state": row.state,
            "recommendation_type": "teacher" if row.reason_code == "teacher_selected" else "personalized",
            "reason_code": row.reason_code,
            "source_signals": safe_source_signals(row.reason_code, row.source_signals),
            "algorithm_version": row.algorithm_version,
            "explanation": explanation_for(safe_source_signals(row.reason_code, row.source_signals), language) if row.reason_code == "personalized_rules" else row.explanation,
            "created_at": row.created_at,
            **visible,
        })
    LearningAuditEvent.objects.create(
        actor=request.user, school_id=profile.school_id,
        scope="school" if profile.school_id else "public",
        action="learner_recommendations_read",
        target_type="learning_profile", target_id=str(profile.pk),
        safe_details={"count": len(results)},
    )
    return Response({"results": results, "truncated": len(rows) > 50})


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, ActiveLearnerSelfService])
@throttle_classes([LearningProfileThrottle])
def respond_to_recommendation(request, recommendation_id):
    if not isinstance(request.data, dict) or set(request.data) != {"state"}:
        return Response({"detail": "Provide state as accepted or dismissed."}, status=400)
    state = request.data.get("state")
    if state not in {"accepted", "dismissed"}:
        return Response({"detail": "state must be accepted or dismissed."}, status=400)
    profile = request.learning_profile
    with transaction.atomic():
        row = LearningRecommendation.objects.select_for_update().filter(
            pk=recommendation_id, profile=profile,
        ).first()
        if row is None:
            return Response({"detail": "Recommendation not found."}, status=404)
        if row.state not in {"shown", "accepted"}:
            return Response({"detail": "This recommendation is no longer available."}, status=409)
        row.state = state
        row.responded_at = timezone.now()
        row.save(update_fields=["state", "responded_at"])
        LearningAuditEvent.objects.create(
            actor=request.user, school_id=profile.school_id,
            scope="school" if profile.school_id else "public",
            action="learner_recommendation_response",
            target_type="recommendation", target_id=str(row.pk),
            safe_details={"state": state},
        )
    return Response({"id": row.pk, "state": row.state})
