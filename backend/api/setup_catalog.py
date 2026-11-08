from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower, Trim
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from schools.models import (
    ClassLevel,
    Subject,
    SubjectDefinition,
    normalize_school_type,
)
from .setup_views import _caller
from .suspension import SchoolNotSuspended


# Shared catalogue levels are read-only. These ranges only select rows already
# present in Marian's fixture-backed catalogue; they do not create curriculum data.
CATALOG_LEVEL_RULES = {
    "primary": (("CBC", 1, 6),),
    "junior": (("CBC", 7, 9),),
    "combined": (("CBC", 1, 9),),
    "senior": (("CBC", 10, 12), ("844", None, None)),
}

INTERNAL_CODE_NOTICE = (
    "Codes shown here are Marian internal catalogue codes, not official ministry or KNEC codes. "
    "Verify names and codes against the current official list before relying on them."
)


def _catalog_levels(school_type):
    rules = CATALOG_LEVEL_RULES.get(normalize_school_type(school_type))
    if not rules:
        return ClassLevel.objects.none()
    query = None
    for curriculum_code, low, high in rules:
        current = {
            "curriculum__code__iexact": curriculum_code,
            "curriculum__is_active": True,
            "is_active": True,
        }
        if low is not None:
            current["level_number__gte"] = low
            current["level_number__lte"] = high
        part = Q(**current)
        query = part if query is None else query | part
    return ClassLevel.objects.filter(query).select_related("curriculum").order_by(
        "curriculum__code", "level_number", "id"
    )


def _subject_name(definition, level):
    return f"{definition.name} — {level.name}"


def _catalog_rows(school):
    levels = list(_catalog_levels(school.school_type))
    definitions = SubjectDefinition.objects.filter(
        curriculum_id__in={level.curriculum_id for level in levels},
        is_active=True,
    ).prefetch_related("class_levels").order_by("name", "code", "id")
    by_level = {level.id: [] for level in levels}
    existing = list(Subject.objects.filter(school=school).only("id", "name", "code", "definition_id"))
    existing_names = {row.name.strip().casefold(): row for row in existing}
    for definition in definitions:
        definition_levels = {level.id for level in definition.class_levels.all()}
        for level in levels:
            if level.id not in definition_levels:
                continue
            proposed_name = _subject_name(definition, level)
            already = existing_names.get(proposed_name.casefold())
            by_level[level.id].append({
                "definition_id": definition.id,
                "class_level_id": level.id,
                "name": definition.name,
                "code": definition.code,
                "marian_internal_code": definition.code,
                "subject_name": proposed_name,
                "already_added": bool(already),
                "subject_id": already.id if already else None,
            })
    return levels, by_level


def _school_admin(request):
    profile = _caller(request)
    if not profile or profile.is_deputy:
        return None
    return profile


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
def subject_catalog(request):
    profile = _caller(request)
    if not profile:
        return Response({"detail": "You are not allowed to do that."}, status=403)
    levels, by_level = _catalog_rows(profile.school)
    school_type = normalize_school_type(profile.school.school_type)
    if school_type not in CATALOG_LEVEL_RULES:
        return Response({"detail": "Choose a school type before loading subjects."}, status=400)
    groups = []
    for level in levels:
        rows = sorted(by_level[level.id], key=lambda row: (row["name"].casefold(), row["code"], row["definition_id"]))
        groups.append({
            "curriculum_code": level.curriculum.code,
            "curriculum_name": level.curriculum.name,
            "class_level_id": level.id,
            "class_level_name": level.name,
            "level_number": level.level_number,
            "subjects": rows,
        })
    return Response({
        "school_type": school_type,
        "groups": groups,
        "marian_internal_codes": True,
        "notice": INTERNAL_CODE_NOTICE,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
def add_catalog_subjects(request):
    profile = _school_admin(request)
    if not profile:
        return Response({"detail": "Only the school administrator can add subjects."}, status=403)
    selections = request.data.get("selections", request.data.get("items", []))
    if not isinstance(selections, list) or not selections:
        return Response({"detail": "Select at least one subject."}, status=400)
    allowed_levels = set(_catalog_levels(profile.school.school_type).values_list("id", flat=True))
    created = []
    skipped = []
    seen = set()
    with transaction.atomic():
        for item in selections:
            try:
                definition_id = int(item.get("definition_id"))
                class_level_id = int(item.get("class_level_id"))
            except (AttributeError, TypeError, ValueError):
                return Response({"detail": "Each selection needs a valid subject and level."}, status=400)
            key = (definition_id, class_level_id)
            if key in seen:
                skipped.append({"definition_id": definition_id, "class_level_id": class_level_id, "reason": "duplicate_selection"})
                continue
            seen.add(key)
            if class_level_id not in allowed_levels:
                return Response({"detail": "That class level is not available for this school type."}, status=400)
            definition = SubjectDefinition.objects.filter(
                pk=definition_id, is_active=True, class_levels__id=class_level_id,
            ).select_related("curriculum").first()
            level = ClassLevel.objects.filter(pk=class_level_id, is_active=True).select_related("curriculum").first()
            if definition is None or level is None:
                return Response({"detail": "That subject is not in the current Marian catalogue for this level."}, status=400)
            name = _subject_name(definition, level)
            existing = Subject.objects.annotate(
                _normalized_name=Lower(Trim("name")),
            ).filter(
                school=profile.school,
                _normalized_name=name.strip().lower(),
            ).first()
            if existing:
                skipped.append({
                    "definition_id": definition.id,
                    "class_level_id": level.id,
                    "name": name,
                    "code": definition.code,
                    "reason": "already_exists",
                    "subject_id": existing.id,
                })
                continue
            try:
                with transaction.atomic():
                    subject, was_created = Subject.objects.get_or_create(
                        school=profile.school,
                        name=name,
                        defaults={
                            "code": definition.code,
                            "definition": definition,
                            "is_active": True,
                        },
                    )
            except IntegrityError:
                subject = Subject.objects.annotate(
                    _normalized_name=Lower(Trim("name")),
                ).filter(
                    school=profile.school,
                    _normalized_name=name.strip().lower(),
                ).first()
                if subject is None:
                    return Response({"detail": "That subject could not be added right now."}, status=409)
                was_created = False
            if was_created:
                created.append({
                    "id": subject.id,
                    "definition_id": definition.id,
                    "class_level_id": level.id,
                    "name": subject.name,
                    "code": subject.code,
                })
            else:
                skipped.append({
                    "definition_id": definition.id,
                    "class_level_id": level.id,
                    "name": subject.name,
                    "code": subject.code,
                    "reason": "already_exists",
                    "subject_id": subject.id,
                })
    return Response({
        "created": created,
        "skipped": skipped,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "marian_internal_codes": True,
        "notice": INTERNAL_CODE_NOTICE,
    }, status=201 if created else 200)
