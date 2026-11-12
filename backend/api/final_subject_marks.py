from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, Exam, FinalSubjectMark, MarkAuditLog, SchoolAdminProfile,
    Subject, SubjectRegistration,
)
from .permissions import get_user_school_id
from .views import _scope

MAX_BATCH = 3000
TRANSITIONS = {
    "submit": ("draft", "submitted"),
    "approve": ("submitted", "approved"),
    "reject": ("submitted", "draft"),
    "lock": ("approved", "locked"),
}


def _admin(user, school_id):
    return user.is_superuser or SchoolAdminProfile.objects.filter(user=user, school_id=school_id).exists()


def _positive_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _reason(request):
    reason = request.data.get("reason")
    return reason.strip() if isinstance(reason, str) and 3 <= len(reason.strip()) <= 1000 else None


def _serialize(row):
    return {
        "id": row.id,
        "exam": row.exam_id,
        "student": row.student_id,
        "subject": row.subject_id,
        "marks": str(row.marks) if row.marks is not None else None,
        "mark_status": row.mark_status,
        "status": row.status,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _audit(row, user, action, details=None):
    MarkAuditLog.objects.create(
        school_id=row.exam.school_id, user=user, action=action,
        details={"final_subject_mark": row.id, "exam": row.exam_id,
                 "student_id": row.student_id, "subject_id": row.subject_id,
                 **(details or {})},
    )


@api_view(["GET", "POST"])
def final_subject_mark_collection(request):
    school_id, error = _scope(request)
    if error:
        return error
    if request.method == "GET":
        queryset = FinalSubjectMark.objects.select_related("exam", "student", "subject")
        if school_id is not None:
            queryset = queryset.filter(exam__school_id=school_id)
        for key, field in (("exam", "exam_id"), ("student", "student_id"), ("subject", "subject_id")):
            value = request.query_params.get(key)
            if value:
                numeric = _positive_int(value)
                if not numeric:
                    return Response({"detail": f"Invalid {key} filter."}, status=400)
                queryset = queryset.filter(**{field: numeric})
        return Response([_serialize(row) for row in queryset.order_by("student_id", "subject_id")])

    exam_id = _positive_int(request.data.get("exam"))
    subject_id = _positive_int(request.data.get("subject"))
    entries = request.data.get("entries")
    if not exam_id or not subject_id or not isinstance(entries, list) or not entries:
        return Response({"detail": "exam, subject, and a non-empty entries list are required."}, status=400)
    if len(entries) > MAX_BATCH:
        return Response({"detail": f"A batch may contain at most {MAX_BATCH} final marks."}, status=400)

    with transaction.atomic():
        exam = Exam.objects.select_for_update().select_related("term__academic_year").filter(pk=exam_id).first()
        if exam is None:
            return Response({"detail": "Examination not found."}, status=404)
        if school_id is not None and exam.school_id != school_id:
            return Response({"detail": "Examination does not belong to your school."}, status=403)
        if not _admin(request.user, exam.school_id):
            return Response({"detail": "Only a school administrator can enter direct final subject marks."}, status=403)
        if exam.status != "draft":
            return Response({"detail": "Final subject marks can only be entered for a draft examination."}, status=409)
        subject = Subject.objects.filter(pk=subject_id, school_id=exam.school_id, is_active=True).first()
        if subject is None:
            return Response({"detail": "Subject not found or inactive."}, status=404)

        student_ids = {_positive_int(item.get("student")) for item in entries if isinstance(item, dict)}
        student_ids.discard(None)
        enrollments = {
            row.student_id: row for row in Enrollment.objects.filter(
                student_id__in=student_ids, academic_year=exam.term.academic_year,
                class_level=exam.class_level, is_active=True,
                student__school_id=exam.school_id,
            ).select_related("student")
        }
        registered = set(SubjectRegistration.objects.filter(
            student_id__in=student_ids, academic_year=exam.term.academic_year, subject=subject,
        ).values_list("student_id", flat=True))
        errors = []
        prepared = []
        seen = set()
        allowed = {choice[0] for choice in FinalSubjectMark.MARK_STATUS_CHOICES}
        for index, item in enumerate(entries):
            if not isinstance(item, dict):
                errors.append({"index": index, "detail": "Each entry must be an object."}); continue
            student_id = _positive_int(item.get("student"))
            if not student_id or student_id in seen:
                errors.append({"index": index, "detail": "Each student must appear once with a valid id."}); continue
            seen.add(student_id)
            if student_id not in enrollments:
                errors.append({"index": index, "student": student_id, "detail": "Learner is not actively enrolled in this examination's class and academic year."}); continue
            if student_id not in registered:
                errors.append({"index": index, "student": student_id, "detail": "Learner is not registered for this subject in this academic year."}); continue
            status = item.get("mark_status", "scored")
            value = item.get("marks")
            if status not in allowed:
                errors.append({"index": index, "student": student_id, "detail": "Choose a supported mark status."}); continue
            if status == "scored":
                if value in (None, "") or isinstance(value, bool):
                    errors.append({"index": index, "student": student_id, "detail": "A numeric final mark is required; zero is valid."}); continue
                try:
                    value = Decimal(str(value))
                except (InvalidOperation, ValueError):
                    errors.append({"index": index, "student": student_id, "detail": "Final mark must be numeric."}); continue
                if value < 0 or value > 100:
                    errors.append({"index": index, "student": student_id, "detail": "Final mark must be between 0 and 100."}); continue
            elif value not in (None, ""):
                errors.append({"index": index, "student": student_id, "detail": "Non-scored statuses must not include a numeric mark."}); continue
            else:
                value = None
            prepared.append((student_id, value, status))
        if errors:
            return Response({"detail": "Correct the invalid final subject marks; no changes were applied.", "errors": errors}, status=400)

        existing = {
            row.student_id: row for row in FinalSubjectMark.objects.select_for_update().filter(
                exam=exam, subject=subject, student_id__in=[row[0] for row in prepared]
            )
        }
        saved = 0
        for student_id, value, status in prepared:
            row = existing.get(student_id)
            if row is None:
                row = FinalSubjectMark.objects.create(exam=exam, student_id=student_id, subject=subject,
                                                       marks=value, mark_status=status, entered_by=request.user, status="draft")
                _audit(row, request.user, "final_created", {"marks": str(value) if value is not None else None, "mark_status": status})
                saved += 1
                continue
            if row.status == "locked":
                errors.append({"student": student_id, "detail": "Locked final marks cannot be changed."}); continue
            if row.status in ("submitted", "approved"):
                reason = _reason(request)
                if reason is None:
                    errors.append({"student": student_id, "detail": "A correction reason of 3–1000 characters is required for submitted or approved final marks."}); continue
                before = {"marks": str(row.marks) if row.marks is not None else None, "mark_status": row.mark_status, "status": row.status}
                row.status = "submitted" if row.status == "approved" else row.status
                _audit(row, request.user, "final_corrected", {"reason": reason, "before": before})
            row.marks, row.mark_status, row.entered_by = value, status, request.user
            row.save(update_fields=["marks", "mark_status", "entered_by", "status", "updated_at"])
            saved += 1
        if errors:
            return Response({"detail": "Some final marks could not be saved; no changes were applied.", "errors": errors}, status=409)
    return Response({"exam": exam.id, "subject": subject.id, "saved": saved, "mode": "direct_final_subject_mark"}, status=200)


@api_view(["POST"])
def final_subject_mark_action(request, pk, action):
    if action not in TRANSITIONS:
        return Response({"detail": "Unknown action."}, status=400)
    with transaction.atomic():
        row = FinalSubjectMark.objects.select_for_update().select_related("exam", "subject", "student").filter(pk=pk).first()
        if row is None:
            return Response({"detail": "Final subject mark not found."}, status=404)
        if not _admin(request.user, row.exam.school_id):
            return Response({"detail": "Only a school administrator can change final subject mark workflow status."}, status=403)
        required, new_status = TRANSITIONS[action]
        if row.status != required:
            return Response({"detail": f"Final mark is '{row.status}'; '{action}' needs '{required}'."}, status=409)
        if action == "approve" and row.mark_status == "pending":
            return Response({"detail": "Pending final marks cannot be approved."}, status=409)
        reason = _reason(request) if action in ("approve", "reject") else None
        if action in ("approve", "reject") and reason is None:
            return Response({"reason": ["A decision reason of 3–1000 characters is required."]}, status=400)
        before = row.status; row.status = new_status; row.save(update_fields=["status", "updated_at"])
        _audit(row, request.user, f"final_{action}", {"from": before, "to": new_status, "reason": reason})
    return Response({**_serialize(row), "action": action})
