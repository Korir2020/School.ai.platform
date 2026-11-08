from rest_framework.decorators import api_view
from rest_framework.response import Response

from collections import defaultdict
from decimal import Decimal

from schools.models import (
    Enrollment, Exam, ExamResult, LevelResult, SchoolAdminProfile,
    ReportSettings, Student, SubjectRegistration,
)
from .permissions import get_user_school_id
from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS


def _admin_scope(request):
    """Return (school_id, error). school_id None + no error = superuser."""
    if request.user.is_superuser:
        return None, None
    if not SchoolAdminProfile.objects.filter(user=request.user).exists():
        return None, Response({"detail": "Admins only."}, status=403)
    return get_user_school_id(request.user), None


@api_view(["GET"])
def exam_results(request, pk):
    school_id, error = _admin_scope(request)
    if error:
        return error
    exams = Exam.objects.all()
    if school_id is not None:
        exams = exams.filter(school_id=school_id)
    exam = exams.filter(pk=pk).first()
    if exam is None:
        return Response({"detail": "Not found."}, status=404)
    if exam.status != "published":
        return Response({"detail": "Exam is not published yet."}, status=409)
    if exam.framework_key in CBC_REPORT_FRAMEWORKS and not ExamResult.objects.filter(exam=exam).exists():
        enrollments = list(Enrollment.objects.filter(
            academic_year=exam.term.academic_year, class_level=exam.class_level,
            is_active=True, student__school_id=exam.school_id,
        ).select_related("student", "stream", "pathway"))
        student_by_id = {row.student_id: row.student for row in enrollments}
        stream_by_id = {row.student_id: (row.stream.name if row.stream else "") for row in enrollments}
        pathway_by_id = {row.student_id: {
            "pathway": row.pathway.name if row.pathway else "",
            "pathway_code": row.pathway.code if row.pathway else "",
        } for row in enrollments}
        registrations = defaultdict(set)
        registration_names = defaultdict(list)
        for sid, subject_id, subject_name in SubjectRegistration.objects.filter(
            academic_year=exam.term.academic_year, student_id__in=student_by_id,
            subject__school_id=exam.school_id,
        ).values_list("student_id", "subject_id", "subject__name"):
            registrations[sid].add(subject_id)
            registration_names[sid].append(subject_name)
        levels = list(LevelResult.objects.filter(
            student_id__in=student_by_id, academic_year=exam.term.academic_year,
            term=exam.term, assessment_type=exam.assessment_type,
            status__in=["approved", "locked"], subject__school_id=exam.school_id,
        ).select_related("subject", "scale"))
        by_student = defaultdict(dict)
        distribution = defaultdict(int)
        by_stream = defaultdict(lambda: defaultdict(int))
        for row in levels:
            if row.subject_id not in registrations.get(row.student_id, set()):
                continue
            desc = next((item for item in row.scale.levels
                         if item.get("key") == row.level_key), None)
            if desc is None:
                continue
            by_student[row.student_id][row.subject.name] = {
                "key": row.level_key, "label": desc.get("label", row.level_key),
                "description": desc.get("description", ""),
            }
            distribution[desc.get("label", row.level_key)] += 1
            by_stream[stream_by_id.get(row.student_id, "")][desc.get("label", row.level_key)] += 1
        result_rows = []
        for sid, subject_scores in by_student.items():
            student = student_by_id[sid]
            counts = defaultdict(int)
            for descriptor in subject_scores.values():
                counts[descriptor["label"]] += 1
            summary = " · ".join(f"{label}: {n}" for label, n in counts.items())
            result_rows.append({
                "student_id": sid, "name": f"{student.first_name} {student.last_name}",
                "admission_number": student.admission_number,
                "overall_average": None, "overall_summary": summary,
                "stream_rank": None, "class_rank": None,
                "subject_scores": subject_scores, "subject_statuses": {},
                "stream": stream_by_id.get(sid, ""),
                **pathway_by_id.get(sid, {"pathway": "", "pathway_code": ""}),
                "subject_combination": sorted(registration_names.get(sid, [])),
            })
        stage = {"cbe_primary": "Primary", "cbe_junior_levels": "Junior",
                 "cbe_senior": "Senior"}.get(exam.framework_key, "CBC")
        official_notice = ("not official KNEC" if stage == "Primary"
                           else "not an official KNEC assessment")
        return Response({
            "exam": exam.name, "framework_key": exam.framework_key,
            "result_mode": "achievement_levels",
            "notice": f"School-defined CBC {stage} achievement levels; internal school assessment, {official_notice}. No numeric ranking was calculated.",
            "results": sorted(result_rows, key=lambda row: row["admission_number"]),
            "performance_summary": {
                "class": dict(distribution),
                "streams": {stream: dict(counts) for stream, counts in by_stream.items()},
            },
            "rankings_enabled": False,
        })
    rankings_enabled = True
    if exam.framework_key in CBC_REPORT_FRAMEWORKS:
        settings_row = ReportSettings.objects.filter(school_id=exam.school_id).first()
        rankings_enabled = bool((settings_row.sections if settings_row else {}).get("positions", False))
    school_scheme = None
    if exam.framework_key in CBC_REPORT_FRAMEWORKS:
        try:
            from .report_views import service as report_service
            school_scheme = report_service(exam.school_id, exam.id).scheme
        except Exception:
            # Numeric results remain readable even if a legacy exam lacks its
            # frozen rule payload; no replacement national defaults are used.
            school_scheme = None

    def grade_for(value):
        if school_scheme is None or value is None:
            return None
        try:
            return school_scheme.grade_for(school_scheme.quantize(Decimal(str(value)))).label
        except Exception:
            return None

    results = (
        ExamResult.objects.filter(exam=exam)
        .select_related("student")
        .order_by("class_rank", "student__admission_number")
    )
    result_student_ids = list(results.values_list("student_id", flat=True))
    enrollment_by_student = {
        row.student_id: row for row in Enrollment.objects.filter(
            student_id__in=result_student_ids, academic_year=exam.term.academic_year,
            class_level=exam.class_level, is_active=True,
        ).select_related("pathway")
    }
    registered_names = defaultdict(list)
    for sid, name in SubjectRegistration.objects.filter(
        student_id__in=enrollment_by_student, academic_year=exam.term.academic_year,
        subject__school_id=exam.school_id,
    ).values_list("student_id", "subject__name"):
        registered_names[sid].append(name)
    return Response({
        "exam": exam.name,
        "framework_key": exam.framework_key,
        "result_mode": "marks",
        "rankings_enabled": rankings_enabled,
        "results": [
            {
                "student_id": r.student_id,
                "name": f"{r.student.first_name} {r.student.last_name}",
                "admission_number": r.student.admission_number,
                "overall_average": str(r.overall_average),
                "overall_grade": grade_for(r.overall_average),
                "stream_rank": r.stream_rank if rankings_enabled else None,
                "class_rank": r.class_rank if rankings_enabled else None,
                "subject_scores": r.subject_scores,
                "subject_grades": ({name: grade_for(value)
                                    for name, value in (r.subject_scores or {}).items()}
                                   if exam.framework_key in CBC_REPORT_FRAMEWORKS else {}),
                "subject_statuses": r.subject_statuses,
                "pathway": (enrollment_by_student[r.student_id].pathway.name
                            if r.student_id in enrollment_by_student and enrollment_by_student[r.student_id].pathway else ""),
                "pathway_code": (enrollment_by_student[r.student_id].pathway.code
                                 if r.student_id in enrollment_by_student and enrollment_by_student[r.student_id].pathway else ""),
                "subject_combination": sorted(registered_names.get(r.student_id, [])),
            }
            for r in results
        ],
    })


@api_view(["GET"])
def student_exam_history(request, student_id):
    school_id, error = _admin_scope(request)
    if error:
        return error
    students = Student.objects.all()
    if school_id is not None:
        students = students.filter(school_id=school_id)
    student = students.filter(pk=student_id).first()
    if student is None:
        return Response({"detail": "Not found."}, status=404)
    results = (
        ExamResult.objects.filter(student=student)
        .select_related("exam__term")
        .order_by("exam__published_at")
    )
    return Response({
        "student": f"{student.first_name} {student.last_name}",
        "history": [
            {
                "exam": r.exam.name,
                "term": r.exam.term.name,
                "assessment_type": r.exam.assessment_type,
                "published_at": r.exam.published_at,
                "overall_average": str(r.overall_average),
                "stream_rank": r.stream_rank,
                "class_rank": r.class_rank,
                "subject_scores": r.subject_scores,
                "subject_statuses": r.subject_statuses,
            }
            for r in results
        ],
    })
