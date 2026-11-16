"""School-admin Learning settings and oversight APIs (Activity 14)."""

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended

from .models import LearningAuditEvent, LearningSchoolSettings
from .permissions import FullSchoolLearningAdmin
from schools.models import TeacherProfile
from .throttles import LearningProfileThrottle


class FullSchoolLearningControlAdmin(FullSchoolLearningAdmin):
    """Only a single-purpose full school-admin identity may change controls."""

    def has_permission(self, request, view):
        return bool(
            super().has_permission(request, view)
            and not TeacherProfile.objects.filter(user=request.user).exists()
        )


SETTING_FIELDS = {
    "learning_access_enabled",
    "teacher_studio_enabled",
    "teacher_recommendations_enabled",
    "minimum_learner_age",
    "maximum_learner_age",
}
BOOLEAN_FIELDS = {
    "learning_access_enabled",
    "teacher_studio_enabled",
    "teacher_recommendations_enabled",
}


def _settings_payload(row):
    return {
        "learning_access_enabled": row.learning_access_enabled,
        "teacher_studio_enabled": row.teacher_studio_enabled,
        "teacher_recommendations_enabled": row.teacher_recommendations_enabled,
        "minimum_learner_age": row.minimum_learner_age,
        "maximum_learner_age": row.maximum_learner_age,
        "updated_at": row.updated_at,
    }


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningControlAdmin])
@throttle_classes([LearningProfileThrottle])
def school_learning_settings(request):
    school_id = request.learning_school_admin.school_id
    row = LearningSchoolSettings.objects.filter(school_id=school_id).first()
    if request.method == "GET":
        if row is None:
            row = LearningSchoolSettings(
                school_id=school_id,
                learning_access_enabled=True,
                teacher_studio_enabled=True,
                teacher_recommendations_enabled=False,
                minimum_learner_age=0,
                maximum_learner_age=120,
            )
        LearningAuditEvent.objects.create(
            actor=request.user, school_id=school_id, scope="school",
            action="school_learning_settings_read", target_type="school", target_id=str(school_id),
        )
        return Response(_settings_payload(row))

    if not isinstance(request.data, dict) or not request.data:
        return Response({"detail": "Provide one or more learning settings."}, status=400)
    unknown = set(request.data) - SETTING_FIELDS
    if unknown:
        return Response({"detail": "Unsupported learning settings: " + ", ".join(sorted(unknown))}, status=400)
    for key in BOOLEAN_FIELDS & set(request.data):
        if not isinstance(request.data[key], bool):
            return Response({"detail": f"{key} must be true or false."}, status=400)
    for key in {"minimum_learner_age", "maximum_learner_age"} & set(request.data):
        value = request.data[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 120:
            return Response({"detail": f"{key} must be a whole-number age from 0 to 120."}, status=400)

    with transaction.atomic():
        row, _created = LearningSchoolSettings.objects.select_for_update().get_or_create(
            school_id=school_id,
            defaults={"updated_by": request.user},
        )
        for key, value in request.data.items():
            setattr(row, key, value)
        row.updated_by = request.user
        try:
            row.full_clean()
        except ValidationError as exc:
            messages = exc.message_dict.values() if hasattr(exc, "message_dict") else [exc.messages]
            return Response({"detail": "; ".join(str(item) for group in messages for item in group)}, status=400)
        row.save()
        LearningAuditEvent.objects.create(
            actor=request.user, school_id=school_id, scope="school",
            action="school_learning_settings_updated", target_type="school", target_id=str(school_id),
            safe_details={"fields": sorted(request.data.keys())},
        )
    return Response(_settings_payload(row))
