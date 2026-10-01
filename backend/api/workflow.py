from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, MarkAuditLog, Performance, SchoolAdminProfile, TeacherAssignment,
)
from .permissions import get_user_school_id

# action: (required current status, new status, who may do it)
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
        student=perf.student, academic_year=perf.academic_year
    ).first()
    if not enrollment or enrollment.stream_id is None:
        return False
    return TeacherAssignment.objects.filter(
        teacher__user=user, subject=perf.subject, stream_id=enrollment.stream_id
    ).exists()


@api_view(["POST"])
def performance_action(request, pk, action):
    if action not in TRANSITIONS:
        return Response({"detail": "Unknown action."}, status=400)

    queryset = Performance.objects.select_related("student")
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

    old = perf.status
    perf.status = new_status
    perf.save()
    MarkAuditLog.objects.create(
        performance=perf, school_id=perf.student.school_id, user=request.user,
        action=action, details={"from": old, "to": new_status},
    )
    return Response({"id": perf.id, "status": perf.status})


from .serializers import PerformanceSerializer


@api_view(["PATCH"])
def performance_edit(request, pk):
    queryset = Performance.objects.select_related("student")
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
    if perf.status != "draft":
        return Response({"detail": "Only draft marks can be edited."}, status=409)
    if "marks" not in request.data:
        return Response({"marks": ["This field is required."]}, status=400)

    old = str(perf.marks)
    serializer = PerformanceSerializer(
        perf, data={"marks": request.data["marks"]}, partial=True
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    perf = serializer.save()
    MarkAuditLog.objects.create(
        performance=perf, school_id=perf.student.school_id, user=request.user,
        action="edited", details={"from": old, "to": str(perf.marks)},
    )
    return Response(serializer.data)
