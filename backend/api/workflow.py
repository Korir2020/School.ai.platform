from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, Exam, MarkAuditLog, Performance, SchoolAdminProfile,
    TeacherAssignment,
)
from .permissions import get_user_school_id
from .serializers import PerformanceSerializer

# action: (required current workflow status, new status, who may do it)
TRANSITIONS = {
    "submit": ("draft", "submitted", "teacher_or_admin"),
    "approve": ("submitted", "approved", "admin"),
    "reject": ("submitted", "draft", "admin"),
    "lock": ("approved", "locked", "admin"),
}


def _is_admin_of(user, school_id):
    if user.is_superuser:
        return True
    return SchoolAdminProfile.objects.filter(user=user, school_id=school_id).exists()


def _is_assigned_teacher(user, perf):
    enrollment = Enrollment.objects.filter(
        student=perf.student, academic_year=perf.academic_year,
        is_active=True,
    ).select_related("class_level").first()
    if not enrollment or enrollment.stream_id is None:
        return False
    return TeacherAssignment.objects.filter(
        teacher__user=user, school_id=perf.student.school_id,
        subject=perf.subject, stream_id=enrollment.stream_id,
    ).exists()


def _reason(request):
    value = request.data.get("reason")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if 3 <= len(value) <= 1000 else None


def _snapshot(perf):
    enrollment = Enrollment.objects.filter(
        student=perf.student, academic_year=perf.academic_year,
    ).select_related("class_level", "stream").order_by("-id").first()
    exam_id = None
    if enrollment:
        exam_id = Exam.objects.filter(
            school_id=perf.student.school_id, term=perf.term,
            class_level_id=enrollment.class_level_id,
            assessment_type=perf.assessment_type,
        ).values_list("id", flat=True).first()
    return {
        "student_id": perf.student_id,
        "subject_id": perf.subject_id,
        "academic_year_id": perf.academic_year_id,
        "term_id": perf.term_id,
        "assessment_type": perf.assessment_type,
        "paper_number": perf.paper_number,
        "exam_id": exam_id,
        "class_level_id": enrollment.class_level_id if enrollment else None,
        "stream_id": enrollment.stream_id if enrollment else None,
    }


def _mark_value(perf):
    return str(perf.marks) if perf.marks is not None else None


@api_view(["POST"])
def performance_action(request, pk, action):
    if action not in TRANSITIONS:
        return Response({"detail": "Unknown action."}, status=400)

    with transaction.atomic():
        queryset = Performance.objects.select_for_update().select_related(
            "student", "subject", "academic_year", "term",
        )
        if not request.user.is_superuser:
            school_id = get_user_school_id(request.user)
            if school_id is None:
                return Response({"detail": "School access not assigned."}, status=403)
            queryset = queryset.filter(student__school_id=school_id)
        perf = queryset.filter(pk=pk).first()
        if perf is None:
            return Response({"detail": "Not found."}, status=404)

        required, new_status, who = TRANSITIONS[action]
        admin = _is_admin_of(request.user, perf.student.school_id)
        allowed = admin or (who == "teacher_or_admin" and _is_assigned_teacher(request.user, perf))
        if not allowed:
            return Response({"detail": "You are not allowed to do this."}, status=403)
        if perf.status != required:
            return Response(
                {"detail": f"Mark is '{perf.status}'; '{action}' needs '{required}'."},
                status=409,
            )
        if action == "approve" and perf.mark_status == "pending":
            return Response({
                "detail": "Pending marks cannot be approved. Enter a score or an explicit final disposition, or return the mark.",
            }, status=409)

        reason = None
        if action in ("approve", "reject"):
            reason = _reason(request)
            if reason is None:
                return Response(
                    {"reason": ["A decision reason of 3–1000 characters is required."]},
                    status=400,
                )

        old_status = perf.status
        before = {"workflow_status": old_status, "mark_status": perf.mark_status,
                  "marks": _mark_value(perf)}
        perf.status = new_status
        perf.save(update_fields=["status", "updated_at"])
        event = "return" if action == "reject" else action
        details = {
            **_snapshot(perf), "from": old_status, "to": new_status,
            "before": before,
            "after": {"workflow_status": new_status,
                      "mark_status": perf.mark_status, "marks": _mark_value(perf)},
        }
        if reason is not None:
            details["reason"] = reason
        MarkAuditLog.objects.create(
            performance=perf, school_id=perf.student.school_id,
            user=request.user, action=event, details=details,
        )
    return Response({"id": perf.id, "status": perf.status, "action": event})


@api_view(["PATCH"])
def performance_edit(request, pk):
    with transaction.atomic():
        queryset = Performance.objects.select_for_update().select_related(
            "student", "subject", "academic_year", "term",
        )
        if not request.user.is_superuser:
            school_id = get_user_school_id(request.user)
            if school_id is None:
                return Response({"detail": "School access not assigned."}, status=403)
            queryset = queryset.filter(student__school_id=school_id)
        perf = queryset.filter(pk=pk).first()
        if perf is None:
            return Response({"detail": "Not found."}, status=404)

        admin = _is_admin_of(request.user, perf.student.school_id)
        if not (admin or _is_assigned_teacher(request.user, perf)):
            return Response({"detail": "You are not allowed to do this."}, status=403)
        if perf.status == "locked":
            return Response({"detail": "Locked marks cannot be changed."}, status=409)
        admin_correction = admin and perf.status in ("submitted", "approved")
        if not admin and perf.status != "draft":
            return Response({"detail": "Only draft marks can be edited."}, status=409)
        if admin and perf.status not in ("draft", "submitted", "approved"):
            return Response({"detail": "This mark cannot be corrected in its current state."}, status=409)
        if not ("marks" in request.data or "mark_status" in request.data):
            return Response({"detail": "marks or mark_status is required."}, status=400)

        reason = None
        if admin_correction:
            reason = _reason(request)
            if reason is None:
                return Response(
                    {"reason": ["A correction reason of 3–1000 characters is required."]},
                    status=400,
                )

        before = {"workflow_status": perf.status, "mark_status": perf.mark_status,
                  "marks": _mark_value(perf)}
        changes = {
            key: request.data[key] for key in ("marks", "mark_status")
            if key in request.data
        }
        serializer = PerformanceSerializer(perf, data=changes, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        perf = serializer.save()
        old_status = before["workflow_status"]
        # Any correction to an approved mark must return through approval again.
        if old_status == "approved":
            perf.status = "submitted"
            perf.save(update_fields=["status", "updated_at"])
        event = "corrected" if admin_correction else "edited"
        details = {
            **_snapshot(perf), "from": old_status, "to": perf.status,
            "before": before,
            "after": {"workflow_status": perf.status,
                      "mark_status": perf.mark_status, "marks": _mark_value(perf)},
        }
        if reason is not None:
            details["reason"] = reason
        MarkAuditLog.objects.create(
            performance=perf, school_id=perf.student.school_id,
            user=request.user, action=event, details=details,
        )
    return Response(serializer.data)
