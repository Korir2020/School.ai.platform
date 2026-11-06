from datetime import date

from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes

from schools.models import AttendanceRecord, Enrollment, SchoolAdminProfile, Student, StudentIntervention, TeacherProfile
from .permissions import get_user_school_id, restrict_for_teacher
from .pagination import StandardPagination
from .views import _scope


def _students(request, school_id):
    qs = restrict_for_teacher(request.user, Student.objects.all())
    if school_id is not None: qs = qs.filter(school_id=school_id)
    class_id, stream_id = request.GET.get("class_level_id"), request.GET.get("stream_id")
    if class_id: qs = qs.filter(enrollment__class_level_id=class_id, enrollment__is_active=True)
    if stream_id: qs = qs.filter(enrollment__stream_id=stream_id, enrollment__is_active=True)
    return qs.distinct().order_by("last_name", "first_name")


def _can_write(user):
    return user.is_superuser or SchoolAdminProfile.objects.filter(user=user).exists() or TeacherProfile.objects.filter(user=user).exists()


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiResponse(description="School-scoped daily attendance roster or save result."), 400: OpenApiResponse(description="Invalid attendance payload."), 403: OpenApiResponse(description="Attendance write permission denied.")})
@api_view(["GET", "POST"])
def attendance_collection(request):
    school_id, error = _scope(request)
    if error: return error
    if request.method == "GET":
        day = request.GET.get("date") or date.today().isoformat()
        try:
            day = date.fromisoformat(day)
        except (TypeError, ValueError):
            return Response({"detail": "Use a valid YYYY-MM-DD date."}, status=400)
        students = _students(request, school_id)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(students, request)
        page_ids = [s.id for s in page]
        records = {
            r.student_id: r for r in AttendanceRecord.objects.filter(
                student_id__in=page_ids, date=day,
            )
        }
        roster = [{
            "id": s.id, "name": str(s), "admission_number": s.admission_number,
            "status": records[s.id].status if s.id in records else "present",
            "notes": records[s.id].notes if s.id in records else "",
        } for s in page]
        response = paginator.get_paginated_response(roster)
        response.data["date"] = day.isoformat()
        # Retain the legacy key for older clients while exposing standard pages.
        response.data["students"] = roster
        return response
    if not _can_write(request.user): return Response({"detail": "You cannot record attendance."}, status=403)
    day, rows = request.data.get("date"), request.data.get("records", [])
    if not isinstance(day, str) or not isinstance(rows, list):
        return Response({"detail": "Date and records are required."}, status=400)
    try:
        day = date.fromisoformat(day)
    except ValueError:
        return Response({"detail": "Use a valid YYYY-MM-DD date."}, status=400)
    if len(rows) > 5000:
        return Response({"detail": "Save at most 5,000 attendance records per batch."}, status=400)

    normalized, seen = [], set()
    allowed_statuses = dict(AttendanceRecord.STATUSES)
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            return Response({"detail": f"Record {index + 1} must be an object."}, status=400)
        raw_id = row.get("student_id")
        if isinstance(raw_id, bool) or not (
            isinstance(raw_id, int)
            or isinstance(raw_id, str) and raw_id.isdigit()
        ):
            return Response({"detail": f"Record {index + 1} has an invalid learner id."}, status=400)
        try:
            student_id = int(raw_id)
        except (TypeError, ValueError):
            return Response({"detail": f"Record {index + 1} has an invalid learner id."}, status=400)
        if student_id <= 0 or student_id in seen:
            return Response({"detail": f"Record {index + 1} has a duplicate or invalid learner id."}, status=400)
        seen.add(student_id)
        status = row.get("status")
        notes = row.get("notes", "")
        if not isinstance(status, str) or status not in allowed_statuses:
            return Response({"detail": f"Record {index + 1} has an invalid attendance status."}, status=400)
        if not isinstance(notes, str) or len(notes) > 255:
            return Response({"detail": f"Record {index + 1} notes must be 255 characters or fewer."}, status=400)
        normalized.append(AttendanceRecord(
            student_id=student_id, date=day, status=status, notes=notes,
            recorded_by=request.user,
        ))

    allowed = set(_students(request, school_id).filter(
        id__in=seen,
    ).values_list("id", flat=True))
    if allowed != seen:
        return Response({"detail": "One or more learners are outside your authorized school or class scope."}, status=403)
    with transaction.atomic():
        AttendanceRecord.objects.bulk_create(
            normalized, batch_size=500, update_conflicts=True,
            update_fields=["status", "notes", "recorded_by"],
            unique_fields=["student", "date"],
        )
    return Response({"saved": len(normalized), "date": day.isoformat()})


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiResponse(description="School-scoped intervention records or update result."), 201: OpenApiResponse(description="Intervention created."), 400: OpenApiResponse(description="Invalid intervention payload."), 403: OpenApiResponse(description="Intervention permission denied."), 404: OpenApiResponse(description="Student or intervention not found.")})
@api_view(["GET", "POST", "PATCH"])
def interventions(request, student_id=None):
    school_id, error = _scope(request)
    if error: return error
    students = restrict_for_teacher(request.user, Student.objects.all())
    if school_id is not None: students = students.filter(school_id=school_id)
    if student_id is not None: students = students.filter(id=student_id)
    student = students.first()
    if not student: return Response({"detail": "Not found."}, status=404)
    if request.method == "GET":
        rows = StudentIntervention.objects.filter(student=student).select_related("created_by")
        return Response([{"id": x.id, "reason": x.reason, "reason_label": x.get_reason_display(), "notes": x.notes, "action_plan": x.action_plan, "follow_up_date": x.follow_up_date, "outcome": x.outcome, "outcome_notes": x.outcome_notes, "created_by": x.created_by.get_username() if x.created_by else "", "created_at": x.created_at} for x in rows])
    if not _can_write(request.user): return Response({"detail": "You cannot manage interventions."}, status=403)
    fields = {"reason", "notes", "action_plan", "follow_up_date", "outcome", "outcome_notes"}
    if request.method == "POST":
        data = {k: request.data.get(k) for k in fields if k in request.data}
        if data.get("reason") not in dict(StudentIntervention.REASONS) or not data.get("notes"): return Response({"detail": "Reason and notes are required."}, status=400)
        x = StudentIntervention.objects.create(student=student, created_by=request.user, **data)
        return Response({"id": x.id}, status=201)
    x = StudentIntervention.objects.filter(student=student, id=request.data.get("id")).first()
    if not x: return Response({"detail": "Intervention not found."}, status=404)
    for key in fields:
        if key in request.data: setattr(x, key, request.data[key])
    x.save(); return Response({"id": x.id, "outcome": x.outcome})
