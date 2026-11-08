from django.db import transaction
from django.utils import timezone
from uuid import uuid4
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, Exam, MarkAuditLog, Performance, SchoolAdminProfile, Subject,
    Stream, SubjectPaper, SubjectRegistration, TeacherAssignment, TeacherProfile,
)
from .serializers import PerformanceSerializer
from .senior_rules import is_cbc_senior, pathway_matches_class, subject_definition_problem
from .views import _scope

MAX_BATCH_CELLS = 3000


def _positive_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        pass
    elif isinstance(value, str) and value.strip().isdecimal():
        value = int(value.strip())
    else:
        return None
    return value if value > 0 else None


def _is_admin(user, school_id):
    return user.is_superuser or SchoolAdminProfile.objects.filter(
        user=user, school_id=school_id,
    ).exists()


def _blank(value):
    return value is None or isinstance(value, str) and not value.strip()


@api_view(["POST"])
def performance_batch(request):
    school_id, error = _scope(request)
    if error:
        return error

    exam_id = _positive_int(request.data.get("exam"))
    subject_id = _positive_int(request.data.get("subject"))
    entries = request.data.get("entries")
    if not exam_id or not subject_id or not isinstance(entries, list):
        return Response({
            "detail": "exam, subject, and an entries list are required."
        }, status=400)
    if not entries:
        return Response({"detail": "Add at least one mark before saving."}, status=400)
    if len(entries) > MAX_BATCH_CELLS:
        return Response({
            "detail": f"A batch may contain at most {MAX_BATCH_CELLS} mark cells."
        }, status=400)

    raw_rows = []
    seen_keys = set()
    problems = []
    student_ids = set()
    paper_numbers = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            problems.append({"index": index, "detail": "Each entry must be an object."})
            continue
        student_id = _positive_int(item.get("student"))
        paper_number = _positive_int(item.get("paper_number"))
        if not student_id or not paper_number:
            problems.append({
                "index": index,
                "detail": "Each entry requires a valid student and paper_number.",
            })
            continue
        key = (student_id, paper_number)
        if key in seen_keys:
            problems.append({
                "index": index,
                "student": student_id,
                "paper_number": paper_number,
                "detail": "Duplicate student and paper entry in this batch.",
            })
        seen_keys.add(key)
        student_ids.add(student_id)
        paper_numbers.add(paper_number)
        raw_rows.append((index, item, student_id, paper_number, key))
    if problems:
        return Response({"detail": "Correct the invalid mark entries.", "errors": problems}, status=400)

    with transaction.atomic():
        exam_qs = Exam.objects.select_for_update().select_related("term__academic_year")
        if school_id is not None:
            exam_qs = exam_qs.filter(school_id=school_id)
        exam = exam_qs.filter(pk=exam_id).first()
        if exam is None:
            return Response({"detail": "Examination not found."}, status=404)
        if exam.status != "draft":
            return Response({"detail": "Marks can only be entered for a draft examination."}, status=409)

        admin = _is_admin(request.user, exam.school_id)
        teacher = request.user.is_superuser or TeacherProfile.objects.filter(
            user=request.user, school_id=exam.school_id,
        ).exists()
        if not (admin or teacher):
            return Response({"detail": "Only assigned teachers and school admins can enter marks."}, status=403)

        subject = Subject.objects.filter(
            pk=subject_id, school_id=exam.school_id, is_active=True,
        ).select_related("definition").prefetch_related(
            "definition__class_levels", "definition__pathways").first()
        if subject is None:
            return Response({"detail": "Assigned subject not found or inactive."}, status=404)

        year = exam.term.academic_year
        enrollments = list(Enrollment.objects.filter(
            student_id__in=student_ids,
            academic_year=year,
            class_level=exam.class_level,
            is_active=True,
            student__school_id=exam.school_id,
        ).select_related("student", "stream", "class_level__curriculum", "pathway"))
        enrollment_by_student = {enrollment.student_id: enrollment for enrollment in enrollments}
        registered_ids = set(SubjectRegistration.objects.filter(
            student_id__in=student_ids,
            academic_year=year,
            subject=subject,
        ).values_list("student_id", flat=True))
        assigned_stream_ids = set()
        if not admin and not request.user.is_superuser:
            assigned_stream_ids = set(TeacherAssignment.objects.filter(
                teacher__user=request.user,
                school_id=exam.school_id,
                subject=subject,
            ).values_list("stream_id", flat=True))

        paper_rows = list(SubjectPaper.objects.filter(subject=subject).order_by("paper_number"))
        paper_by_number = {paper.paper_number: paper for paper in paper_rows}
        if paper_by_number:
            invalid_papers = sorted(paper_numbers - set(paper_by_number))
            if invalid_papers:
                return Response({
                    "detail": "One or more papers are not defined for this subject.",
                    "paper_numbers": invalid_papers,
                }, status=400)
        elif paper_numbers - {1}:
            return Response({
                "detail": "Subjects without configured papers accept Paper 1 only.",
                "paper_numbers": sorted(paper_numbers - {1}),
            }, status=400)

        existing_rows = Performance.objects.select_for_update().filter(
            student_id__in=student_ids,
            subject=subject,
            academic_year=year,
            term=exam.term,
            assessment_type=exam.assessment_type,
            paper_number__in=paper_numbers,
        )
        existing_by_key = {
            (row.student_id, row.paper_number): row for row in existing_rows
        }

        errors, conflicts, forbidden = [], [], []
        creates, updates, deletes = [], [], []
        audit_rows = []
        for index, item, student_id, paper_number, key in raw_rows:
            enrollment = enrollment_by_student.get(student_id)
            if enrollment is None:
                errors.append({
                    "index": index, "student": student_id, "paper_number": paper_number,
                    "detail": "Learner is not actively enrolled in this examination's class and academic year.",
                })
                continue
            if student_id not in registered_ids:
                errors.append({
                    "index": index, "student": student_id, "paper_number": paper_number,
                    "detail": "Learner is not registered for this subject in this academic year.",
                })
                continue
            if is_cbc_senior(enrollment.class_level):
                if not pathway_matches_class(enrollment.pathway, enrollment.class_level):
                    errors.append({
                        "index": index, "student": student_id, "paper_number": paper_number,
                        "detail": "Learner needs an active CBC Senior pathway for this academic year.",
                    })
                    continue
                problem = subject_definition_problem(subject.definition, enrollment.class_level,
                                                     enrollment.pathway)
                if problem:
                    errors.append({"index": index, "student": student_id,
                                   "paper_number": paper_number, "detail": problem})
                    continue
            if not admin and not request.user.is_superuser and (
                enrollment.stream_id is None or enrollment.stream_id not in assigned_stream_ids
            ):
                forbidden.append({
                    "index": index, "student": student_id, "paper_number": paper_number,
                    "detail": "You are not assigned to this subject and learner's stream.",
                })
                continue

            existing = existing_by_key.get(key)
            if existing and existing.status != "draft":
                conflicts.append({
                    "index": index, "student": student_id, "paper_number": paper_number,
                    "detail": f"This mark is {existing.status} and cannot be edited.",
                })
                continue

            mark_value = item.get("marks")
            mark_status = item.get("mark_status", "scored")
            legacy_clear = "mark_status" not in item and _blank(mark_value)
            if legacy_clear:
                if existing is not None:
                    deletes.append(existing)
                    audit_rows.append(MarkAuditLog(
                        school_id=exam.school_id,
                        user=request.user, action="deleted",
                        details={"mark_id": existing.pk, "student": student_id,
                                 "subject": subject_id, "paper_number": paper_number,
                                 "marks": str(existing.marks) if existing.marks is not None else None,
                                 "mark_status": existing.mark_status,
                                 "workflow_status": existing.status, "exam": exam.id,
                                 "reason": "draft cleared during batch edit"},
                    ))
                continue

            allowed_mark_statuses = {choice[0] for choice in Performance.MARK_STATUS_CHOICES}
            if not isinstance(mark_status, str) or mark_status not in allowed_mark_statuses:
                errors.append({
                    "index": index, "student": student_id, "paper_number": paper_number,
                    "errors": {"mark_status": ["Choose a supported mark status."]},
                })
                continue
            if mark_status == "scored":
                if _blank(mark_value) or isinstance(mark_value, bool):
                    errors.append({
                        "index": index, "student": student_id, "paper_number": paper_number,
                        "errors": {"marks": ["A numeric mark is required for a scored entry; zero is valid."]},
                    })
                    continue
            elif not _blank(mark_value):
                errors.append({
                    "index": index, "student": student_id, "paper_number": paper_number,
                    "errors": {"marks": ["Non-scored statuses must not include a numeric mark."]},
                })
                continue
            else:
                mark_value = None

            mark_fields = {
                "student": student_id,
                "subject": subject_id,
                "academic_year": year.id,
                "term": exam.term_id,
                "assessment_type": exam.assessment_type,
                "paper_number": paper_number,
                "marks": mark_value,
                "mark_status": mark_status,
            }
            serializer = PerformanceSerializer(
                existing, data=mark_fields, partial=existing is not None,
            )
            if not serializer.is_valid():
                errors.append({
                    "index": index, "student": student_id, "paper_number": paper_number,
                    "errors": serializer.errors,
                })
                continue
            value = serializer.validated_data["marks"]
            disposition = serializer.validated_data.get("mark_status", mark_status)
            if existing is None:
                creates.append(Performance(
                    student=enrollment.student, subject=subject,
                    academic_year=year, term=exam.term,
                    assessment_type=exam.assessment_type,
                    paper_number=paper_number, marks=value,
                    mark_status=disposition,
                    entered_by=request.user, status="draft",
                ))
                audit_rows.append(MarkAuditLog(
                    school_id=exam.school_id, user=request.user, action="created",
                    details={"student": student_id, "subject": subject_id,
                             "academic_year": year.id, "term": exam.term_id,
                             "assessment_type": exam.assessment_type,
                             "paper_number": paper_number,
                             "marks": str(value) if value is not None else None,
                             "mark_status": disposition, "workflow_status": "draft",
                             "exam": exam.id, "batch": True},
                ))
            elif existing.marks != value or existing.mark_status != disposition:
                previous = {"marks": str(existing.marks) if existing.marks is not None else None,
                            "mark_status": existing.mark_status}
                existing.marks = value
                existing.mark_status = disposition
                existing.updated_at = timezone.now()
                updates.append(existing)
                audit_rows.append(MarkAuditLog(
                    performance=existing, school_id=exam.school_id,
                    user=request.user, action="edited",
                    details={"from": previous,
                             "to": {"marks": str(value) if value is not None else None,
                                    "mark_status": disposition},
                             "workflow_status": existing.status,
                             "student": student_id, "subject": subject_id,
                             "academic_year": year.id, "term": exam.term_id,
                             "assessment_type": exam.assessment_type,
                             "paper_number": paper_number, "exam": exam.id,
                             "batch": True},
                ))

        if conflicts or errors or forbidden:
            status = 403 if forbidden else (409 if conflicts and not errors else 400)
            return Response({
                "detail": "Some mark entries could not be saved; no changes were applied.",
                "errors": errors + conflicts + forbidden,
            }, status=status)

        if deletes:
            Performance.objects.filter(pk__in=[row.pk for row in deletes]).delete()
        if creates:
            Performance.objects.bulk_create(creates, batch_size=500)
        if updates:
            Performance.objects.bulk_update(
                updates, ["marks", "mark_status", "updated_at"], batch_size=500,
            )
        if audit_rows:
            created_by_key = {
                (mark.student_id, mark.subject_id, mark.paper_number): mark
                for mark in creates
            }
            for row in audit_rows:
                if row.action == "created":
                    key = (row.details["student"], row.details["subject"],
                           row.details["paper_number"])
                    row.performance = created_by_key[key]
            MarkAuditLog.objects.bulk_create(audit_rows, batch_size=500)

    return Response({
        "exam": exam.id,
        "subject": subject.id,
        "saved": len(creates) + len(updates),
        "created": len(creates),
        "updated": len(updates),
        "deleted": len(deletes),
    }, status=200)


@api_view(["POST"])
def performance_batch_submit(request):
    school_id, error = _scope(request)
    if error:
        return error
    exam_id = _positive_int(request.data.get("exam"))
    subject_id = _positive_int(request.data.get("subject"))
    stream_id = _positive_int(request.data.get("stream"))
    if not exam_id or not subject_id or not stream_id:
        return Response({"detail": "exam, subject, and stream are required."}, status=400)

    with transaction.atomic():
        exams = Exam.objects.select_for_update().select_related("term__academic_year")
        if school_id is not None:
            exams = exams.filter(school_id=school_id)
        exam = exams.filter(pk=exam_id).first()
        if exam is None:
            return Response({"detail": "Examination not found."}, status=404)
        if exam.status != "draft":
            return Response({"detail": "Only draft examinations accept mark submissions."}, status=409)
        subject = Subject.objects.filter(
            pk=subject_id, school_id=exam.school_id, is_active=True,
        ).first()
        if subject is None:
            return Response({"detail": "Subject not found or inactive."}, status=404)
        stream = Stream.objects.filter(pk=stream_id, class_level=exam.class_level).first()
        if stream is None:
            return Response({"detail": "Stream does not belong to this examination's class."}, status=400)

        admin = _is_admin(request.user, exam.school_id)
        if not admin and not request.user.is_superuser:
            assigned = TeacherAssignment.objects.filter(
                teacher__user=request.user, school_id=exam.school_id,
                subject=subject, stream_id=stream_id,
            ).exists()
            if not assigned:
                return Response({"detail": "You are not assigned to this subject and stream."}, status=403)

        year = exam.term.academic_year
        student_ids = list(Enrollment.objects.filter(
            academic_year=year, class_level=exam.class_level,
            stream_id=stream_id, is_active=True,
            student__school_id=exam.school_id,
        ).values_list("student_id", flat=True))
        registered_ids = SubjectRegistration.objects.filter(
            academic_year=year, subject=subject, student_id__in=student_ids,
        ).values_list("student_id", flat=True)
        rows = list(Performance.objects.select_for_update().filter(
            student_id__in=registered_ids, subject=subject, academic_year=year,
            term=exam.term, assessment_type=exam.assessment_type,
            status="draft",
        ).select_related("student", "subject"))
        resolved = [row for row in rows if row.mark_status != "pending"]
        pending_count = sum(1 for row in rows if row.mark_status == "pending")
        if not resolved:
            return Response({
                "exam": exam.id, "subject": subject.id, "stream": stream.id,
                "submitted": 0, "pending": pending_count,
                "detail": "There are no resolved draft marks to submit.",
            }, status=200)

        operation_id = str(uuid4())
        now = timezone.now()
        for row in resolved:
            row.status = "submitted"
            row.updated_at = now
        Performance.objects.bulk_update(resolved, ["status", "updated_at"], batch_size=500)
        MarkAuditLog.objects.bulk_create([
            MarkAuditLog(
                performance=row, school_id=exam.school_id, user=request.user,
                action="submit",
                details={
                    "operation_id": operation_id, "batch": True,
                    "student_id": row.student_id, "subject_id": row.subject_id,
                    "academic_year_id": row.academic_year_id, "term_id": row.term_id,
                    "assessment_type": row.assessment_type,
                    "paper_number": row.paper_number, "exam_id": exam.id,
                    "stream_id": stream.id,
                    "before": {"workflow_status": "draft",
                               "mark_status": row.mark_status,
                               "marks": str(row.marks) if row.marks is not None else None},
                    "after": {"workflow_status": "submitted",
                              "mark_status": row.mark_status,
                              "marks": str(row.marks) if row.marks is not None else None},
                },
            ) for row in resolved
        ], batch_size=500)

    return Response({
        "exam": exam.id, "subject": subject.id, "stream": stream.id,
        "submitted": len(resolved), "pending": pending_count,
        "operation_id": operation_id,
    }, status=200)
