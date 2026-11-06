from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, Exam, Performance, SchoolAdminProfile, Student,
    SubjectPaper, SubjectRegistration,
)
from .pagination import StandardPagination

READY_WORKFLOW = {"approved", "locked"}


def _empty_stats():
    return {
        "_learner_ids": set(),
        "expected_cells": 0,
        "entered_cells": 0,
        "resolved_cells": 0,
        "missing_marks": 0,
        "pending_approvals": 0,
        "pending_dispositions": 0,
        "draft_marks": 0,
        "submitted_marks": 0,
        "approved_marks": 0,
        "locked_marks": 0,
        "outcomes": {
            "scored": 0, "absent": 0, "exempted": 0,
            "not_assessed": 0, "pending": 0,
        },
        "_score_sum": 0.0,
        "_score_count": 0,
        "_highest": None,
        "_lowest": None,
    }


def _add_cell(stats, mark):
    stats["expected_cells"] += 1
    if mark is None:
        stats["missing_marks"] += 1
        return

    stats["entered_cells"] += 1
    workflow = mark.status
    if workflow == "draft":
        stats["draft_marks"] += 1
    elif workflow == "submitted":
        stats["submitted_marks"] += 1
        stats["pending_approvals"] += 1
    elif workflow == "approved":
        stats["approved_marks"] += 1
    elif workflow == "locked":
        stats["locked_marks"] += 1

    disposition = mark.mark_status
    stats["outcomes"][disposition] = stats["outcomes"].get(disposition, 0) + 1
    if disposition == "pending":
        stats["pending_dispositions"] += 1
        return
    if disposition != "scored" or mark.marks is None:
        # Absent, exempted, and not-assessed are explicit completed outcomes,
        # but none contribute numeric scores.
        stats["resolved_cells"] += 1
        return
    stats["resolved_cells"] += 1


def _finalized_subject_score(marks, papers):
    """Use the same weighted, ready-only scoring policy as exam publication."""
    if any(mark is None or mark.status not in READY_WORKFLOW
           or mark.mark_status == "pending" for mark in marks):
        return None
    weighted_score = Decimal("0")
    counted_weight = Decimal("0")
    for mark, paper in zip(marks, papers):
        weight = paper["weight"]
        if mark.mark_status == "scored":
            maximum = paper["max_marks"] or Decimal("100")
            weighted_score += mark.marks * weight / maximum
            counted_weight += weight
        elif mark.mark_status == "absent":
            # Absence is a completed outcome that contributes zero.
            counted_weight += weight
        # Exemptions and not-assessed papers do not enter the denominator.
    if not counted_weight:
        return None
    return float(weighted_score * Decimal("100") / counted_weight)


def _add_subject_score(stats, score):
    if score is None:
        return
    stats["_score_sum"] += score
    stats["_score_count"] += 1
    stats["_highest"] = score if stats["_highest"] is None else max(stats["_highest"], score)
    stats["_lowest"] = score if stats["_lowest"] is None else min(stats["_lowest"], score)


def _format_stats(stats, enrolled_learners=None):
    expected = stats["expected_cells"]
    return {
        "enrolled_learners": enrolled_learners,
        "registered_learners": len(stats["_learner_ids"]),
        "expected_cells": expected,
        "entered_cells": stats["entered_cells"],
        "resolved_cells": stats["resolved_cells"],
        "missing_marks": stats["missing_marks"],
        "pending_approvals": stats["pending_approvals"],
        "pending_dispositions": stats["pending_dispositions"],
        "draft_marks": stats["draft_marks"],
        "submitted_marks": stats["submitted_marks"],
        "approved_marks": stats["approved_marks"],
        "locked_marks": stats["locked_marks"],
        "outcomes": stats["outcomes"],
        "completion_percentage": round(stats["resolved_cells"] * 100 / expected, 1) if expected else None,
        "approval_percentage": round((stats["approved_marks"] + stats["locked_marks"]) * 100 / expected, 1) if expected else None,
        "average_score_pct": round(stats["_score_sum"] / stats["_score_count"], 2) if stats["_score_count"] else None,
        "highest_score_pct": round(stats["_highest"], 2) if stats["_highest"] is not None else None,
        "lowest_score_pct": round(stats["_lowest"], 2) if stats["_lowest"] is not None else None,
        "finalized_subject_scores": stats["_score_count"],
    }


def _positive_id(value, name):
    if value is None or value == "":
        return None, None
    if not str(value).isdigit() or int(value) <= 0:
        return None, f"Invalid {name}."
    return int(value), None


@api_view(["GET"])
def admin_exam_dashboard(request):
    admin = SchoolAdminProfile.objects.filter(user=request.user).select_related("school").first()
    if admin is None:
        return Response({"detail": "School administrators only."}, status=403)
    school_id = admin.school_id

    exam_id, error = _positive_id(request.query_params.get("exam_id"), "exam_id")
    if error or exam_id is None:
        return Response({"detail": error or "exam_id is required."}, status=400)
    exam = Exam.objects.filter(
        id=exam_id, school_id=school_id,
        term__academic_year__school_id=school_id,
    ).select_related("term__academic_year", "class_level").first()
    if exam is None:
        return Response({"detail": "Examination not found."}, status=404)

    stream_param = request.query_params.get("stream_id", "")
    subject_param = request.query_params.get("subject_id", "")
    if stream_param and stream_param != "unassigned":
        stream_id, error = _positive_id(stream_param, "stream_id")
        if error:
            return Response({"detail": error}, status=400)
        stream_id = str(stream_id)
    else:
        stream_id = stream_param or None
    subject_id, error = _positive_id(subject_param, "subject_id")
    if error:
        return Response({"detail": error}, status=400)

    enrollment_rows = Enrollment.objects.filter(
        student__school_id=school_id,
        student__status="active",
        academic_year_id=exam.term.academic_year_id,
        class_level_id=exam.class_level_id,
        is_active=True,
    ).filter(
        Q(stream__isnull=True) | Q(stream__school_id=school_id),
    ).select_related("student", "stream").order_by("student_id", "-id")
    enrollment_by_student = {}
    for enrollment in enrollment_rows:
        enrollment_by_student.setdefault(enrollment.student_id, enrollment)
    student_ids = list(enrollment_by_student)
    stream_key_by_student = {
        student_id: str(enrollment.stream_id) if enrollment.stream_id else "unassigned"
        for student_id, enrollment in enrollment_by_student.items()
    }

    stream_learners = defaultdict(int)
    stream_names = {"unassigned": "Unassigned stream"}
    for enrollment in enrollment_by_student.values():
        key = str(enrollment.stream_id) if enrollment.stream_id else "unassigned"
        stream_learners[key] += 1
        if enrollment.stream_id:
            stream_names[key] = enrollment.stream.name
    if stream_id and stream_id not in stream_learners:
        return Response({"detail": "Stream is not part of this examination roster."}, status=400)

    scope_student_ids = (
        [student_id for student_id in student_ids
         if stream_key_by_student[student_id] == stream_id]
        if stream_id else student_ids
    )
    registrations = list(SubjectRegistration.objects.filter(
        academic_year_id=exam.term.academic_year_id,
        student_id__in=scope_student_ids,
        subject__school_id=school_id,
    ).select_related("subject").order_by("subject__name", "student_id"))
    subject_names = {reg.subject_id: reg.subject.name for reg in registrations}
    subject_ids = sorted(subject_names)
    papers_by_subject = defaultdict(list)
    configured_papers = SubjectPaper.objects.filter(
        subject_id__in=subject_ids,
    ).order_by("subject_id", "paper_number")
    for paper in configured_papers:
        papers_by_subject[paper.subject_id].append({
            "paper_number": paper.paper_number,
            "max_marks": paper.max_marks,
            "weight": paper.weight,
        })
    for subject_key in subject_ids:
        if not papers_by_subject[subject_key]:
            papers_by_subject[subject_key] = [{
                "paper_number": 1, "max_marks": Decimal("100"), "weight": Decimal("100"),
            }]

    expected_numbers = sorted({
        paper["paper_number"]
        for papers in papers_by_subject.values()
        for paper in papers
    })
    marks = Performance.objects.filter(
        student_id__in=scope_student_ids,
        subject_id__in=subject_ids,
        term_id=exam.term_id,
        academic_year_id=exam.term.academic_year_id,
        assessment_type=exam.assessment_type,
        paper_number__in=expected_numbers,
    ).select_related("subject")
    marks_by_cell = {
        (mark.student_id, mark.subject_id, mark.paper_number): mark for mark in marks
    }

    all_stats = _empty_stats()
    streams_stats = defaultdict(_empty_stats)
    subjects_stats = defaultdict(_empty_stats)
    stream_subject_stats = defaultdict(_empty_stats)
    registrations_by_subject_student = defaultdict(list)
    registration_streams_by_subject = defaultdict(set)

    for registration in registrations:
        student_key = registration.student_id
        subject_key = registration.subject_id
        stream_key = stream_key_by_student[student_key]
        targets = (
            all_stats,
            streams_stats[stream_key],
            subjects_stats[subject_key],
            stream_subject_stats[(stream_key, subject_key)],
        )
        for target in targets:
            target["_learner_ids"].add(student_key)
        registrations_by_subject_student[(subject_key, student_key)].append(registration)
        registration_streams_by_subject[subject_key].add(stream_key)
        registration_marks = []
        for paper in papers_by_subject[subject_key]:
            mark = marks_by_cell.get((student_key, subject_key, paper["paper_number"]))
            registration_marks.append(mark)
            for target in targets:
                _add_cell(target, mark)
        subject_score = _finalized_subject_score(
            registration_marks, papers_by_subject[subject_key],
        )
        for target in targets:
            _add_subject_score(target, subject_score)

    if subject_id is not None:
        valid_subjects = {
            key for key, stream_keys in registration_streams_by_subject.items()
            if not stream_id or stream_id in stream_keys
        }
        if subject_id not in valid_subjects:
            return Response({"detail": "Subject has no registered learners in this dashboard scope."}, status=400)

    if subject_id is not None:
        selected_stats = (
            stream_subject_stats[(stream_id, subject_id)] if stream_id
            else subjects_stats[subject_id]
        )
    elif stream_id:
        selected_stats = streams_stats[stream_id]
    else:
        selected_stats = all_stats
    selected_enrolled = (
        sum(1 for key in stream_key_by_student.values() if not stream_id or key == stream_id)
        if subject_id is None
        else len(selected_stats["_learner_ids"])
    )

    streams = []
    for key in sorted(stream_learners, key=lambda item: stream_names.get(item, item).casefold()):
        stats = streams_stats[key]
        streams.append({
            "id": key,
            "name": stream_names[key],
            "learner_count": stream_learners[key],
            "progress": _format_stats(stats, stream_learners[key]),
        })

    available_subject_ids = [
        key for key in subject_ids
        if not stream_id or stream_id in registration_streams_by_subject[key]
    ]
    subjects = []
    for key in sorted(available_subject_ids, key=lambda item: subject_names[item].casefold()):
        stats = stream_subject_stats[(stream_id, key)] if stream_id else subjects_stats[key]
        subjects.append({
            "id": key,
            "name": subject_names[key],
            "registration_count": len(stats["_learner_ids"]),
            "papers": [paper["paper_number"] for paper in papers_by_subject[key]],
            "progress": _format_stats(stats, len(stats["_learner_ids"])),
        })

    learner_page = None
    if subject_id is not None:
        learner_ids = {
            student_key for (subj_key, student_key) in registrations_by_subject_student
            if subj_key == subject_id
            and (not stream_id or stream_key_by_student[student_key] == stream_id)
        }
        learners = sorted(
            (enrollment_by_student[key].student for key in learner_ids),
            key=lambda student: (
                (student.admission_number or "").casefold(),
                student.first_name.casefold(), student.last_name.casefold(), student.id,
            ),
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(learners, request)
        learner_rows = []
        for student in page:
            enrollment = enrollment_by_student[student.id]
            key = str(enrollment.stream_id) if enrollment.stream_id else "unassigned"
            paper_rows = []
            for paper in papers_by_subject[subject_id]:
                mark = marks_by_cell.get((student.id, subject_id, paper["paper_number"]))
                paper_rows.append({
                    "paper_number": paper["paper_number"],
                    "max_marks": str(paper["max_marks"]),
                    "mark": str(mark.marks) if mark and mark.marks is not None else None,
                    "mark_status": mark.mark_status if mark else "missing",
                    "workflow_status": mark.status if mark else None,
                })
            learner_rows.append({
                "id": student.id,
                "name": str(student),
                "admission_number": student.admission_number,
                "stream": stream_names[key],
                "papers": paper_rows,
            })
        learner_page = paginator.get_paginated_response(learner_rows).data

    return Response({
        "exam": {
            "id": exam.id, "name": exam.name,
            "term": exam.term.name,
            "academic_year": exam.term.academic_year.name,
            "assessment_type": exam.assessment_type,
            "status": exam.status,
            "class_level": {"id": exam.class_level_id, "name": exam.class_level.name},
        },
        "selected_stream_id": stream_id or "",
        "selected_subject_id": subject_id,
        "summary": _format_stats(selected_stats, selected_enrolled),
        "streams": streams,
        "subjects": subjects,
        "paper_definitions": ([
            {
                "paper_number": paper["paper_number"],
                "max_marks": str(paper["max_marks"]),
                "weight": str(paper["weight"]),
            } for paper in papers_by_subject.get(subject_id, [])
        ] if subject_id is not None else []),
        "learners": learner_page,
    })
