from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, Exam, ExamResult, MarkAuditLog, Performance,
    SchoolAdminProfile, SubjectPaper,
)
from .permissions import get_user_school_id

HUNDRED = Decimal("100")
READY = ("approved", "locked")


def _rank(value, values):
    return 1 + sum(1 for v in values if v > value)


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
            student__school_id=exam.school_id,
        ).select_related("student")
    )
    students = {e.student_id: e.student for e in enrollments}
    stream_of = {e.student_id: e.stream_id for e in enrollments}

    marks = list(
        Performance.objects.filter(
            term=exam.term, assessment_type=exam.assessment_type,
            student_id__in=students.keys(),
        ).select_related("subject")
    )
    if not marks:
        return Response({"detail": "No marks entered for this exam."}, status=400)

    papers = defaultdict(dict)
    for sp in SubjectPaper.objects.filter(subject_id__in={m.subject_id for m in marks}):
        papers[sp.subject_id][sp.paper_number] = sp.weight
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

    problems, scores, counted = [], {}, []
    for student_id, subjects in grouped.items():
        subject_scores = {}
        for subject_id, got in subjects.items():
            weights = papers.get(subject_id) or {1: HUNDRED}
            missing = [n for n in weights if n not in got or got[n].status not in READY]
            if missing:
                problems.append({
                    "admission_number": students[student_id].admission_number,
                    "subject": names[subject_id],
                    "papers_not_ready": sorted(missing),
                })
                continue
            subject_scores[subject_id] = sum(
                got[n].marks * w / HUNDRED for n, w in weights.items()
            )
            counted.extend(got[n] for n in weights)
        scores[student_id] = subject_scores
    if problems:
        return Response({
            "detail": "Some papers are incomplete or not approved.",
            "count": len(problems), "problems": problems[:20],
        }, status=409)

    overall = {
        sid: (sum(subj.values()) / len(subj)).quantize(Decimal("0.01"))
        for sid, subj in scores.items()
    }
    class_values = list(overall.values())
    stream_values = defaultdict(list)
    for sid, value in overall.items():
        stream_values[stream_of[sid]].append(value)

    with transaction.atomic():
        ExamResult.objects.bulk_create([
            ExamResult(
                exam=exam, student_id=sid, overall_average=value,
                stream_rank=(
                    _rank(value, stream_values[stream_of[sid]])
                    if stream_of[sid] is not None else None
                ),
                class_rank=_rank(value, class_values),
                subject_scores={
                    names[s]: str(v.quantize(Decimal("0.01")))
                    for s, v in scores[sid].items()
                },
            )
            for sid, value in overall.items()
        ])
        approved = [m for m in counted if m.status == "approved"]
        Performance.objects.filter(pk__in=[m.pk for m in approved]).update(status="locked")
        MarkAuditLog.objects.bulk_create([
            MarkAuditLog(
                performance=m, school_id=exam.school_id, user=request.user,
                action="lock",
                details={"from": "approved", "to": "locked", "exam": exam.id},
            )
            for m in approved
        ])
        exam.status = "published"
        exam.published_at = timezone.now()
        exam.published_by = request.user
        exam.save()

    return Response({"exam": exam.id, "status": "published", "students_ranked": len(overall)})
