from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .suspension import SchoolNotSuspended
from rest_framework.response import Response

from schools.models import (
    AcademicYear, MarkAuditLog, School, SchoolAdminProfile, Stream, Subject, Term,
)

NO = "You are not allowed to do that."


def compute_checklist(school):
    return {
        "profile": bool(
            school.name
            and (school.location or "").strip()
            and (school.county or "").strip()
            and (school.school_type or "").strip()
        ),
        "academic_year": AcademicYear.objects.filter(school=school, is_active=True).exists(),
        "term": Term.objects.filter(academic_year__school=school, is_active=True).exists(),
        "stream": Stream.objects.filter(school=school, is_active=True).exists(),
        "subject": Subject.objects.filter(school=school, is_active=True).exists(),
    }


def _caller(request):
    return (
        SchoolAdminProfile.objects.select_related("school")
        .filter(user=request.user, user__is_active=True)
        .first()
    )


def _payload(school, checklist):
    return {
        "setup_complete": school.setup_completed_at is not None,
        "completed_at": school.setup_completed_at,
        "checklist": checklist,
        "missing": [k for k, v in checklist.items() if not v],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
def setup_status(request):
    profile = _caller(request)
    if not profile:
        return Response({"detail": NO}, status=403)
    school = profile.school
    return Response(_payload(school, compute_checklist(school)))


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
def setup_complete(request):
    profile = _caller(request)
    if not profile or profile.is_deputy:
        return Response({"detail": NO}, status=403)
    with transaction.atomic():
        school = School.objects.select_for_update().get(pk=profile.school_id)
        if school.setup_completed_at:
            return Response(_payload(school, compute_checklist(school)))
        checklist = compute_checklist(school)
        payload = _payload(school, checklist)
        if payload["missing"]:
            payload["detail"] = "Setup is incomplete."
            return Response(payload, status=400)
        school.setup_completed_at = timezone.now()
        school.save(update_fields=["setup_completed_at"])
        MarkAuditLog.objects.create(
            school=school, user=request.user, action="setup_completed",
            details={"checklist": checklist},
        )
        return Response(_payload(school, checklist))
