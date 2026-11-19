"""Marian platform-wide content (Stage 1). Publish gate stays closed."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import content_api as ca
from django.contrib.auth import get_user_model
from .models import LearningAuditEvent, LearningContentRole, LearningResource
from .permissions import MarianContentAuthor, MarianContentCurator

EDITABLE = {"draft", "changes_requested"}


def _audit(request, obj, action, **details):
    LearningAuditEvent.objects.create(
        actor=request.user, school=None, scope="public", action=action,
        target_type="resource", target_id=str(obj.pk), safe_details=details,
    )


def _own(request):
    return LearningResource.objects.filter(
        scope="public", author=request.user
    ).select_related("author", "reviewed_by").prefetch_related("topics", "frameworks")


def _lock(request, pk, own):
    qs = LearningResource.objects.select_for_update().filter(pk=pk, scope="public")
    return (qs.filter(author=request.user) if own else qs).first()


def _nf():
    return Response({"detail": "Learning content not found."}, status=404)


def _save(request, obj, data, creating):
    try:
        rows = ca._set_resource_fields(obj, data)
        if not creating:
            if obj.status not in EDITABLE:
                return Response({"detail": "Only a draft or changes-requested version can be edited."}, status=409)
            obj.status = "draft"
            obj.version += 1
            obj.reviewed_by = None
            obj.reviewed_at = None
        if obj.origin == "external" and not obj.external_url:
            return Response({"detail": "External resources require an HTTPS source URL."}, status=400)
        ca._clean_model(obj)
        with transaction.atomic():
            obj.save()
            if rows[0] is not None:
                obj.frameworks.set(rows[0])
            if rows[1] is not None:
                obj.topics.set(rows[1])
            ca._record_revision(obj, request.user)
            _audit(request, obj, "platform_resource_draft_created" if creating else "platform_resource_draft_updated", version=obj.version)
    except (ValueError, DjangoValidationError) as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response(ca._resource_json(obj), status=201 if creating else 200)


@api_view(["GET", "POST"])
@permission_classes([MarianContentAuthor])
def platform_resources(request):
    if request.method == "GET":
        rows = list(_own(request).order_by("-updated_at", "-id")[:100])
        return Response({"results": [ca._resource_json(o) for o in rows]})
    data, error = ca._body_object(request)
    if error:
        return error
    if not data:
        return Response({"detail": "Content fields are required."}, status=400)
    obj = LearningResource(scope="public", school=None, author=request.user, status="draft", version=1)
    return _save(request, obj, data, True)


@api_view(["GET", "PATCH"])
@permission_classes([MarianContentAuthor])
def platform_resource_detail(request, resource_id):
    if request.method == "GET":
        obj = _own(request).filter(pk=resource_id).first()
        return Response(ca._resource_json(obj)) if obj else _nf()
    data, error = ca._body_object(request)
    if error:
        return error
    if not data:
        return Response({"detail": "Provide at least one content field to update."}, status=400)
    with transaction.atomic():
        obj = _lock(request, resource_id, True)
        if obj is None:
            return _nf()
        return _save(request, obj, data, False)


@api_view(["POST"])
@permission_classes([MarianContentAuthor])
def platform_resource_submit(request, resource_id):
    data, error = ca._body_object(request)
    if error:
        return error
    if data:
        return Response({"detail": "This transition does not accept client-supplied content or status fields."}, status=400)
    with transaction.atomic():
        obj = _lock(request, resource_id, True)
        if obj is None:
            return _nf()
        if obj.status not in EDITABLE:
            return Response({"detail": "Only a draft or changes-requested version can be submitted."}, status=409)
        problem = ca._metadata_error(obj)
        if problem:
            return Response({"detail": problem}, status=400)
        obj.status = "in_review"
        obj.reviewed_by = None
        obj.reviewed_at = None
        obj.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        _audit(request, obj, "platform_resource_submitted", version=obj.version)
    return Response(ca._resource_json(obj))


@api_view(["POST"])
@permission_classes([MarianContentCurator])
def platform_resource_review(request, resource_id):
    data, error = ca._body_object(request)
    if error:
        return error
    if set(data) - {"decision"}:
        return Response({"detail": "Review accepts only a decision."}, status=400)
    decision = data.get("decision")
    if decision not in ("approve", "request_changes"):
        return Response({"detail": "decision must be approve or request_changes."}, status=400)
    with transaction.atomic():
        obj = _lock(request, resource_id, False)
        if obj is None:
            return _nf()
        if obj.status != "in_review":
            return Response({"detail": "Only submitted content can be reviewed."}, status=409)
        if obj.author_id == request.user.pk:
            return Response({"detail": "Authors cannot review their own content."}, status=403)
        problem = ca._metadata_error(obj)
        if problem:
            return Response({"detail": problem}, status=400)
        obj.status = "approved" if decision == "approve" else "changes_requested"
        obj.reviewed_by = request.user
        obj.reviewed_at = timezone.now()
        obj.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        _audit(request, obj, "platform_resource_" + obj.status, version=obj.version)
    return Response(ca._resource_json(obj))


@api_view(["POST"])
@permission_classes([MarianContentCurator])
def platform_resource_publish(request, resource_id):
    # Fail-closed gate: nothing is published until a separate approved change.
    obj = LearningResource.objects.filter(pk=resource_id, scope="public").first()
    if obj is None:
        return _nf()
    _audit(request, obj, "platform_resource_publication_blocked", status=obj.status, version=obj.version)
    return Response({
        "code": "content_publication_policy_unapproved",
        "detail": "Publishing is disabled until licensing/rights, moderation/review, and shared-catalogue ownership policies are approved.",
    }, status=503)


@api_view(["GET"])
@permission_classes([MarianContentCurator])
def platform_review_queue(request):
    rows = list(
        LearningResource.objects.filter(scope="public", status="in_review")
        .exclude(author=request.user).order_by("-updated_at", "-id")[:100]
    )
    return Response({"results": [ca._resource_json(o) for o in rows]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def platform_role_grant(request):
    if not request.user.is_superuser:
        return Response({"detail": "Only a superuser can grant content roles."}, status=403)
    data, error = ca._body_object(request)
    if error:
        return error
    role = data.get("role")
    if role not in (LearningContentRole.AUTHOR, LearningContentRole.CURATOR):
        return Response({"detail": "role must be author or curator."}, status=400)
    target = get_user_model().objects.filter(pk=data.get("user_id")).first() if isinstance(data.get("user_id"), int) else None
    if target is None:
        return Response({"detail": "User not found."}, status=404)
    with transaction.atomic():
        row, _ = LearningContentRole.objects.update_or_create(
            user=target, role=role,
            defaults={"is_active": True, "granted_by": request.user},
        )
        LearningAuditEvent.objects.create(
            actor=request.user, school=None, scope="public",
            action="content_role_granted", target_type="user",
            target_id=str(target.pk), safe_details={"role": role},
        )
    return Response({"user_id": target.pk, "role": role, "is_active": True}, status=201)
