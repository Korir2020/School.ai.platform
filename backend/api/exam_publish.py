from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, Exam, ExamResult, LevelResult, MarkAuditLog, Performance,
    SchoolAdminProfile, SubjectPaper, SubjectRegistration,
)
from .permissions import get_user_school_id
from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS
from .senior_rules import is_cbc_senior, pathway_matches_class, subject_definition_problem

HUNDRED = Decimal("100")
READY = ("approved", "locked")
def _publish_cbc_levels(request, exam, students, registered_by_student):
    """Publish school-authored CBC descriptors without numeric scores or ranks."""
    stage = {"cbe_primary": "Primary", "cbe_junior_levels": "Junior",
             "cbe_senior": "Senior"}.get(exam.framework_key, "CBC")
    subject_ids = {sid for values in registered_by_student.values() for sid in values}
    rows = list(LevelResult.objects.filter(
        student_id__in=students, subject_id__in=subject_ids,
        academic_year_id=exam.term.academic_year_id, term=exam.term,
        assessment_type=exam.assessment_type,
    ).select_related("scale", "subject", "student"))
    ready = {(row.student_id, row.subject_id): row for row in rows
             if row.status in READY
             and row.subject_id in registered_by_student.get(row.student_id, set())}
    problems = []
    for student_id, subject_set in registered_by_student.items():
        for subject_id in subject_set:
            row = ready.get((student_id, subject_id))
            if row is None:
                problems.append({"admission_number": students[student_id].admission_number,
                                 "subject_id": subject_id,
                                 "reason": "Approved achievement level is missing."})
            elif (row.scale.school_id != exam.school_id
                  or not row.scale.covers(exam.class_level)
                  or row.level_key not in row.scale.keys()):
                problems.append({"admission_number": students[student_id].admission_number,
                                 "subject_id": subject_id,
                                 "reason": f"Achievement scale does not match this CBC {stage} grade."})
    if len({row.scale_id for row in ready.values()}) > 1:
        problems.append({"reason": f"Use one school-authored CBC {stage} descriptor-scale version for this examination."})
    if not ready:
        return Response({"detail": f"No approved CBC {stage} achievement levels are available."}, status=400)
    if problems:
        return Response({"detail": f"Every registered CBC {stage} learning area needs an approved school-defined level.",
                         "count": len(problems), "problems": problems[:30]}, status=409)

    with transaction.atomic():
        locked_exam = Exam.objects.select_for_update().get(pk=exam.pk)
        if locked_exam.status != "draft":
            return Response({"detail": "Exam is already published."}, status=409)
        approved_rows = [row for row in ready.values() if row.status == "approved"]
        LevelResult.objects.filter(pk__in=[row.pk for row in approved_rows]).update(status="locked")
        MarkAuditLog.objects.bulk_create([
            MarkAuditLog(
                school_id=exam.school_id, user=request.user, action="level_lock",
                details={"level_result": row.pk, "from": "approved", "to": "locked",
                         "exam": exam.pk, "student_id": row.student_id,
                         "subject_id": row.subject_id, "assessment_type": row.assessment_type},
            ) for row in approved_rows
        ])
        from api.framework_rules import record_on_exam
        record_on_exam(locked_exam)
        locked_exam.status = "published"
        locked_exam.published_at = timezone.now()
        locked_exam.published_by = request.user
        locked_exam.save()
        MarkAuditLog.objects.create(
            school_id=exam.school_id, user=request.user, action="publish",
            details={"exam": exam.pk, "result_mode": "achievement_levels",
                     "completed": len(ready), "ranked": 0},
        )
    return Response({"exam": exam.pk, "status": "published",
                     "result_mode": "achievement_levels", "students_ranked": 0,
                     "students_with_levels": len({sid for sid, _ in ready})})


def _rank(value, values):
    return 1 + sum(1 for v in values if v > value)


def _rank_map(values):
    """Competition ranks (1, 1, 3) from one sort rather than one scan per row."""
    ranks, position = {}, 0
    for value in sorted(values, reverse=True):
        ranks.setdefault(value, position + 1)
        position += 1
    return ranks


@api_view(["POST"])
def exam_publish(request, pk):
    exams = Exam.objects.select_related("term__academic_year")
    if not request.user.is_superuser:
        if not SchoolAdminProfile.objects.filter(user=request.user).exists():
            return Response({"detail": "Admins only."}, status=403)
        exams = exams.filter(school_id=get_user_school_id(request.user))
    exam = exams.filter(pk=pk).first()
    if exam is None:
        return Response({"detail": "Not found."}, status=404)
    if exam.status != "draft":
        return Response({"detail": "Exam is already published."}, status=409)

    enrollments = list(
        Enrollment.objects.filter(
            academic_year=exam.term.academic_year,
            class_level=exam.class_level,
            is_active=True,
            student__school_id=exam.school_id,
        ).select_related("student", "class_level__curriculum", "pathway")
    )
    students = {e.student_id: e.student for e in enrollments}
    enrollment_by_student = {e.student_id: e for e in enrollments}
    stream_of = {e.student_id: e.stream_id for e in enrollments}
    from api.framework_rules import resolve
    framework = resolve(exam.school_id, exam.class_level, exam.term.academic_year)
    registered_by_student = defaultdict(set)
    registration_names = {}
    pathway_problems = []
    for registration in SubjectRegistration.objects.filter(
        academic_year=exam.term.academic_year,
        student_id__in=students.keys(),
        subject__school_id=exam.school_id,
    ).select_related("subject__definition").prefetch_related(
        "subject__definition__class_levels", "subject__definition__pathways"):
        enrollment = enrollment_by_student.get(registration.student_id)
        if is_cbc_senior(exam.class_level):
            if enrollment is None or not pathway_matches_class(enrollment.pathway, exam.class_level):
                pathway_problems.append({"admission_number": students[registration.student_id].admission_number,
                                         "reason": "A valid CBC Senior pathway is required."})
                continue
            problem = subject_definition_problem(registration.subject.definition,
                                                 exam.class_level, enrollment.pathway)
            if problem:
                pathway_problems.append({"admission_number": students[registration.student_id].admission_number,
                                         "subject_id": registration.subject_id,
                                         "reason": problem})
                continue
        registered_by_student[registration.student_id].add(registration.subject_id)
        registration_names[registration.subject_id] = registration.subject.name
    if pathway_problems:
        return Response({"detail": "CBC Senior pathway registrations must be corrected before publication.",
                         "count": len(pathway_problems), "problems": pathway_problems[:30]}, status=409)
    if is_cbc_senior(exam.class_level):
        missing_subject_sets = [students[sid].admission_number for sid in set(students) - set(registered_by_student)]
        if missing_subject_sets:
            return Response({"detail": "Every CBC Senior learner needs an individual registered subject combination before publication.",
                             "admission_numbers": missing_subject_sets[:30]}, status=409)
    if not registered_by_student:
        return Response({
            "detail": "No learners in this class have registered subjects for the academic year."
        }, status=400)

    marks = list(
        Performance.objects.filter(
            term=exam.term, assessment_type=exam.assessment_type,
            student_id__in=students.keys(),
        ).select_related("subject")
    )
    # Legacy/imported marks for unregistered subjects remain stored but are
    # deliberately invisible to this exam and its ranks.
    marks = [m for m in marks if m.subject_id in registered_by_student.get(m.student_id, set())]
    if framework is not None and framework.framework_key in CBC_REPORT_FRAMEWORKS and not marks:
        exam.framework_key = framework.framework_key
        return _publish_cbc_levels(request, exam, students, registered_by_student)
    if not marks:
        return Response({"detail": "No marks entered for registered subjects in this exam."}, status=400)
    if framework is not None and framework.framework_key in CBC_REPORT_FRAMEWORKS:
        registered_subject_ids = {subject_id for values in registered_by_student.values()
                                  for subject_id in values}
        mixed_levels = LevelResult.objects.filter(
            student_id__in=students, subject_id__in=registered_subject_ids,
            academic_year_id=exam.term.academic_year_id, term=exam.term,
            assessment_type=exam.assessment_type, status__in=READY,
        ).exists()
        if mixed_levels:
            return Response({"detail": "Choose either numeric school marks or school-authored achievement levels for this CBC exam; mixed modalities cannot be published together."}, status=409)

    papers = defaultdict(dict)
    maxes = defaultdict(dict)
    for sp in SubjectPaper.objects.filter(subject_id__in={m.subject_id for m in marks}):
        papers[sp.subject_id][sp.paper_number] = sp.weight
        maxes[sp.subject_id][sp.paper_number] = sp.max_marks
    bad = sorted({
        m.subject.name for m in marks
        if papers.get(m.subject_id) and sum(papers[m.subject_id].values()) != HUNDRED
    })
    if bad:
        return Response({"detail": "Paper weights must total 100.", "subjects": bad}, status=400)

    grouped = defaultdict(lambda: defaultdict(dict))
    names = {}
    for m in marks:
        grouped[m.student_id][m.subject_id][m.paper_number] = m
        names[m.subject_id] = m.subject.name

    gaps = {}
    for student_id, entered in grouped.items():
        missing = registered_by_student.get(student_id, set()) - set(entered)
        if missing:
            gaps[student_id] = sorted(registration_names[s] for s in missing)
    if gaps:
        found = [{
            "admission_number": students[s].admission_number,
            "name": f"{students[s].first_name} {students[s].last_name}",
            "missing_subjects": g,
        } for s, g in gaps.items()]
        return Response({
            "detail": "Some students have marks for some subjects but not all. "
                      "Enter a score or select an explicit disposition for every registered subject.",
            "count": len(found), "problems": found[:20],
        }, status=409)
    not_ranked = [{
        "admission_number": st.admission_number,
        "name": f"{st.first_name} {st.last_name}",
        "reason": ("No subjects registered for this academic year"
                   if not registered_by_student.get(sid)
                   else "No exam marks entered (did not sit)"),
    } for sid, st in students.items() if sid not in grouped]

    problems, scores, statuses, counted = [], {}, {}, []
    for student_id, subjects in grouped.items():
        subject_scores = {}
        student_statuses = {}
        for subject_id, got in subjects.items():
            weights = papers.get(subject_id) or {1: HUNDRED}
            missing = [
                n for n in weights
                if n not in got or got[n].status not in READY
                or got[n].mark_status == "pending"
            ]
            if missing:
                problems.append({
                    "admission_number": students[student_id].admission_number,
                    "subject": names[subject_id],
                    "papers_not_ready": sorted(missing),
                })
                continue
            weighted_score = Decimal("0")
            counted_weight = Decimal("0")
            student_statuses[names[subject_id]] = {}
            for number, weight in weights.items():
                mark = got[number]
                student_statuses[names[subject_id]][str(number)] = mark.mark_status
                counted.append(mark)
                if mark.mark_status == "scored":
                    weighted_score += mark.marks * weight / maxes.get(subject_id, {}).get(number, HUNDRED)
                    counted_weight += weight
                elif mark.mark_status == "absent":
                    # Absence is complete and distinct from a scored zero; it contributes zero.
                    counted_weight += weight
                # Exempted and not-assessed papers are excluded from the denominator.
            if counted_weight:
                subject_scores[subject_id] = weighted_score * HUNDRED / counted_weight
        scores[student_id] = subject_scores
        statuses[student_id] = student_statuses
    if problems:
        return Response({
            "detail": "Some papers are incomplete or not approved.",
            "count": len(problems), "problems": problems[:20],
        }, status=409)

    already_not_ranked = {row["admission_number"] for row in not_ranked}
    for sid, subject_scores in scores.items():
        if not subject_scores and students[sid].admission_number not in already_not_ranked:
            not_ranked.append({
                "admission_number": students[sid].admission_number,
                "name": f"{students[sid].first_name} {students[sid].last_name}",
                "reason": "All registered subjects were exempted or not assessed",
                "subject_statuses": statuses.get(sid, {}),
            })

    primary_ranks = {}
    rankings_enabled = True
    if framework is not None and framework.framework_key in CBC_REPORT_FRAMEWORKS:
        # Use the same configured mean, exclusions, rank basis, and tie policy
        # that the printed CBC report cards will use.
        try:
            from api.report_views import service as report_service
            from marian_reports.domain import User as ReportUser
            primary_report = report_service(exam.school_id, exam.id)
            rankings_enabled = bool(primary_report.cfg.sections.get("positions", False))
            report_user = ReportUser(
                id=str(request.user.pk), school_id=str(exam.school_id), role="admin",
                class_names=("*",), student_ids=(),
            )
            snapshot = primary_report.snapshot(report_user, str(exam.id), exam.class_level.name)
        except Exception as exc:
            from marian_reports.domain import ReportNotReady
            from marian_reports.grading import GradingError
            if isinstance(exc, (ReportNotReady, GradingError)):
                stage = {"cbe_primary": "Primary", "cbe_junior_levels": "Junior",
                         "cbe_senior": "Senior"}.get(framework.framework_key, "CBC")
                return Response({"detail": f"CBC {stage} school grading rules must be configured before publication: {exc}"}, status=400)
            raise
        overall = {}
        for sid, summary in snapshot.summaries.items():
            if summary.mean_pct is not None:
                overall[int(sid)] = summary.mean_pct.quantize(Decimal("0.01"))
        if rankings_enabled:
            for sid in overall:
                key = str(sid)
                stream = snapshot.students[key].stream
                primary_ranks[sid] = {
                    "class": snapshot.overall.ranks.get(key),
                    "stream": snapshot.stream.get(stream).ranks.get(key)
                    if snapshot.stream.get(stream) else None,
                }
    else:
        overall = {
            sid: (sum(subj.values()) / len(subj)).quantize(Decimal("0.01"))
            for sid, subj in scores.items() if subj
        }
    class_values = list(overall.values())
    stream_values = defaultdict(list)
    for sid, value in overall.items():
        stream_values[stream_of[sid]].append(value)
    class_ranks = _rank_map(class_values) if framework is None or framework.framework_key not in CBC_REPORT_FRAMEWORKS else {}
    stream_ranks = ({
        stream_id: _rank_map(values)
        for stream_id, values in stream_values.items()
    } if framework is None or framework.framework_key not in CBC_REPORT_FRAMEWORKS else {})

    with transaction.atomic():
        locked = Exam.objects.select_for_update().get(pk=exam.pk)
        if locked.status != "draft":
            return Response({"detail": "Exam is already published."}, status=409)
        ExamResult.objects.bulk_create([
            ExamResult(
                exam=exam, student_id=sid, overall_average=value,
                stream_rank=(primary_ranks.get(sid, {}).get("stream")
                             if framework and framework.framework_key in CBC_REPORT_FRAMEWORKS
                             else (stream_ranks[stream_of[sid]][value]
                                   if stream_of[sid] is not None else None)),
                class_rank=(primary_ranks.get(sid, {}).get("class")
                            if framework and framework.framework_key in CBC_REPORT_FRAMEWORKS
                            else class_ranks[value]),
                subject_scores={
                    names[s]: str(v.quantize(Decimal("0.01")))
                    for s, v in scores[sid].items()
                },
                subject_statuses=statuses.get(sid, {}),
            )
            for sid, value in overall.items()
        ])
        approved = [m for m in counted if m.status == "approved"]
        Performance.objects.filter(pk__in=[m.pk for m in approved]).update(status="locked")
        MarkAuditLog.objects.bulk_create([
            MarkAuditLog(
                performance=m, school_id=exam.school_id, user=request.user,
                action="lock",
                details={
                    "from": "approved", "to": "locked", "exam": exam.id,
                    "student_id": m.student_id, "subject_id": m.subject_id,
                    "academic_year_id": m.academic_year_id, "term_id": m.term_id,
                    "assessment_type": m.assessment_type,
                    "paper_number": m.paper_number,
                    "mark_status": m.mark_status,
                    "marks": str(m.marks) if m.marks is not None else None,
                },
            )
            for m in approved
        ])
        MarkAuditLog.objects.create(
            school_id=exam.school_id, user=request.user, action="publish",
            details={"exam": exam.id, "ranked": len(overall) if rankings_enabled else 0,
                     "rankings_enabled": rankings_enabled,
                     "not_ranked": [n["admission_number"] for n in not_ranked]},
        )
        from api.framework_rules import record_on_exam
        record_on_exam(exam)
        exam.status = "published"
        exam.published_at = timezone.now()
        exam.published_by = request.user
        exam.save()

    return Response({"exam": exam.id, "status": "published",
                     "ranked": len(overall) if rankings_enabled else 0,
                     "students_ranked": len(overall) if rankings_enabled else 0,
                     "rankings_enabled": rankings_enabled,
                     "not_ranked": not_ranked})
