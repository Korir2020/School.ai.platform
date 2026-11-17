"""Teacher confirmation of quiz-pass path steps (evidence is not completion)."""
from django.db import transaction
from django.utils import timezone

from .models import LearningProfile, LearningStepCompletion
from .staff_api import (
    IsAuthenticated,
    LearningProfileThrottle,
    Response,
    SchoolNotSuspended,
    TeacherLearningStudio,
    _audit,
    _teacher_assigned_students,
    api_view,
    permission_classes,
    throttle_classes,
)


def _assigned_profile_ids(teacher):
    students = _teacher_assigned_students(teacher)
    return LearningProfile.objects.filter(
        school_id=teacher.school_id,
        account_kind="school_student",
        student_id__in=students.values("pk"),
    ).values("pk")


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningProfileThrottle])
def teacher_step_confirmations(request):
    """Steps where an assigned learner met the pass mark; no scores or answers."""
    teacher = request.learning_school_teacher
    rows = list(
        LearningStepCompletion.objects.filter(
            profile_id__in=_assigned_profile_ids(teacher),
            state="awaiting_confirmation",
            method="teacher",
        )
        .select_related("profile__student", "resource")
        .order_by("created_at", "pk")[:201]
    )
    truncated = len(rows) > 200
    rows = rows[:200]
    _audit(request, "step_confirmations_read",
           details={"count": len(rows), "truncated": truncated})
    return Response({
        "results": [{
            "id": row.pk,
            "student_name": f"{row.profile.student.first_name} {row.profile.student.last_name}".strip(),
            "resource_title": row.resource.title,
            "path_id": row.path_id,
            "item_position": row.item_position,
            "state": row.state,
            "met_pass_mark_at": row.created_at,
        } for row in rows],
        "truncated": truncated,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, TeacherLearningStudio])
@throttle_classes([LearningProfileThrottle])
def decide_step_confirmation(request, completion_id):
    teacher = request.learning_school_teacher
    decision = request.data.get("decision")
    if decision not in ("confirm", "reject"):
        return Response({"detail": "decision must be confirm or reject."}, status=400)
    with transaction.atomic():
        row = LearningStepCompletion.objects.select_for_update().filter(
            pk=completion_id,
            profile_id__in=_assigned_profile_ids(teacher),
            method="teacher",
        ).first()
        if row is None:
            return Response({"detail": "Step confirmation not found."}, status=404)
        if row.state != "awaiting_confirmation":
            return Response({"detail": "This step is not awaiting confirmation."}, status=409)
        row.state = "confirmed" if decision == "confirm" else "rejected"
        row.decided_by = request.user
        row.decided_at = timezone.now()
        row.save(update_fields=["state", "decided_by", "decided_at", "updated_at"])
    _audit(request, f"step_completion_{row.state}", target_type="step_completion",
           target_id=row.pk, details={"step_completion_id": row.pk})
    return Response({"id": row.pk, "state": row.state})
