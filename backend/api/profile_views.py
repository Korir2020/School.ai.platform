from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from schools.models import MarkAuditLog, School, SchoolAdminProfile

NO = "You are not allowed to do that."
TYPES = ("primary", "junior", "secondary", "combined")
LIMITS = {"location": 200, "county": 100, "school_type": 30}


def _caller(request):
    return (
        SchoolAdminProfile.objects.select_related("school")
        .filter(user=request.user, user__is_active=True)
        .first()
    )


def _data(school):
    return {
        "name": school.name,
        "location": school.location,
        "county": school.county,
        "school_type": school.school_type,
    }


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def school_profile(request):
    profile = _caller(request)
    if not profile:
        return Response({"detail": NO}, status=403)
    if request.method == "GET":
        return Response(_data(profile.school))
    if profile.is_deputy:
        return Response({"detail": NO}, status=403)
    errors, clean = {}, {}
    for key, limit in LIMITS.items():
        if key not in request.data:
            continue
        value = request.data.get(key)
        if not isinstance(value, str):
            errors[key] = "Enter text."
            continue
        value = value.strip()
        if key == "school_type":
            value = value.lower()
        if not value:
            errors[key] = "This field is required."
        elif len(value) > limit:
            errors[key] = f"Use at most {limit} characters."
        elif key == "school_type" and value not in TYPES:
            errors[key] = "Choose a school type."
        else:
            clean[key] = value
    if errors:
        return Response({"errors": errors}, status=400)
    if not clean:
        return Response({"detail": "Nothing to update."}, status=400)
    with transaction.atomic():
        school = School.objects.select_for_update().get(pk=profile.school_id)
        for key, value in clean.items():
            setattr(school, key, value)
        school.save(update_fields=list(clean))
        MarkAuditLog.objects.create(
            school=school,
            user=request.user,
            action="profile_updated",
            details={"fields": sorted(clean)},
        )
    return Response(_data(school))
