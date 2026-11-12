"""Level-based report card for the level grades: no marks, percentages,
grades or ranks. Only approved or locked levels are printed.
Level wording is set by the school, not official."""
import hashlib
import json
import re

from django.http import HttpResponse
from rest_framework.response import Response

from api.level_rules import _enrollment, scale_for
from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS
from marian_reports.cbc_level_pdf import render_level_report
from schools.models import Exam, LevelResult, Performance, School, Student, SubjectRegistration

PRINTABLE = ("approved", "locked")
ATYPES = {"opener": "Opener", "mid": "Mid-term", "end": "End-term"}


def _pk(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _err(code, message, status):
    return Response({"error": code, "message": message}, status=status)


def approved_rows(student, year, term, atype):
    return list(LevelResult.objects.filter(
        student=student, academic_year=year, term=term, assessment_type=atype,
        status__in=PRINTABLE).select_related("subject", "scale").order_by("subject__name"))


def build_pdf(school_name, learner, adm, class_name, year_name, term_name, atype, levels, rows,
              is_primary=False, is_junior=False, is_senior=False, **details):
    stage = "senior" if is_senior else "junior" if is_junior else "primary" if is_primary else "primary"
    return render_level_report(
        school_name=school_name, learner=learner, adm=adm,
        learner_id=details.get("learner_id", ""), class_name=class_name,
        year_name=year_name, term_name=term_name,
        assessment=ATYPES.get(atype, atype), stage=stage, levels=levels, rows=rows,
        progress=details.get("progress", {}), remarks=details.get("remarks", {}),
        address=details.get("address", ""), phone=details.get("phone", ""),
        motto=details.get("motto", ""), pathway=details.get("pathway", ""),
        combination=details.get("combination", ()), report_no=details.get("report_no", ""),
        verification_token=details.get("verification_token", ""),
    )


def _exam_for(user, exam_id):
    pk = _pk(exam_id)
    if pk is None:
        return None
    return (Exam.objects.filter(pk=pk, school_id=user.school_id)
            .select_related("term__academic_year").first())


def _level_scale(exam, student):
    enr = _enrollment(student, exam.term.academic_year)
    if enr is None:
        return None, None
    return enr, scale_for(student.school_id, enr.class_level)


def _prior_level_map(student, rows, exam, atype):
    """Return the latest earlier approved descriptor for each subject."""
    if not rows:
        return {}
    previous_rows = list(LevelResult.objects.filter(
        student=student, subject_id__in={row.subject_id for row in rows},
        status__in=PRINTABLE,
    ).exclude(pk__in=[row.pk for row in rows]).select_related(
        "scale", "term__academic_year").order_by(
            "academic_year__start_date", "term__start_date", "id"))
    type_order = {"opener": 0, "mid": 1, "end": 2}
    current_key = (exam.term.academic_year.start_date, exam.term.start_date,
                   type_order.get(atype, 2))
    by_subject = {}
    for prior in previous_rows:
        key = (prior.academic_year.start_date, prior.term.start_date,
               type_order.get(prior.assessment_type, 2))
        if key < current_key:
            by_subject.setdefault(prior.subject_id, []).append((key, prior))
    for history in by_subject.values():
        history.sort(key=lambda item: item[0])
    out = {}
    for row in rows:
        choices = by_subject.get(row.subject_id, [])
        if not choices:
            out[row.subject_id] = "First approved record in this report history."
            continue
        prior = choices[-1][1]
        level = next((entry for entry in prior.scale.levels
                      if entry.get("key") == prior.level_key), {})
        label = level.get("label", prior.level_key)
        out[row.subject_id] = (
            f"Earlier approved descriptor: {label} · {prior.term.name} "
            f"{prior.academic_year.name}. Scale versions may differ."
        )
    return out


def level_pdf_response(request, user, st):
    """PDF for one learner if the class uses level wording, else None."""
    exam = _exam_for(user, request.query_params.get("exam_id", ""))
    student = Student.objects.filter(pk=_pk(st.id), school_id=user.school_id).first()
    if exam is None or student is None:
        return None
    if exam.status != "published":
        return _err("report_not_ready", "This exam is not published yet.", 422)
    requested_type = request.query_params.get("type")
    if requested_type and requested_type != exam.assessment_type:
        return _err("report_not_ready", "Report assessment type must match the published exam.", 422)
    from api.published_reports import find_published_report, response_for_published_report
    archived = find_published_report(user.school_id, exam.pk, student.pk)
    if archived is not None:
        if archived.result_mode == "achievement_levels":
            return response_for_published_report(request, archived)
        return None
    enr, scale = _level_scale(exam, student)
    if scale is None:
        return None
    is_primary = exam.framework_key == "cbe_primary"
    is_junior = exam.framework_key == "cbe_junior_levels"
    is_senior = exam.framework_key == "cbe_senior"
    is_cbc_level_stage = exam.framework_key in CBC_REPORT_FRAMEWORKS
    if is_cbc_level_stage and (enr is None or enr.class_level_id != exam.class_level_id):
        stage = "Senior" if is_senior else "Junior" if is_junior else "Primary"
        return _err("report_not_ready", f"Learner is not enrolled in this examination's CBC {stage} grade.", 422)
    atype = exam.assessment_type
    if atype not in ATYPES:
        return _err("report_not_ready", "Unknown assessment type.", 422)
    year, term = exam.term.academic_year, exam.term
    rows = approved_rows(student, year, term, atype)
    if is_cbc_level_stage:
        registered = set(SubjectRegistration.objects.filter(
            student=student, academic_year=year, subject__school_id=student.school_id,
        ).values_list("subject_id", flat=True))
        rows = [row for row in rows if row.subject_id in registered]
        if Performance.objects.filter(
            student=student, term=term, assessment_type=atype,
            subject_id__in=registered,
        ).exists():
            return None
        if not registered:
            return _err("report_not_ready", "No learning areas are registered for this learner and academic year.", 422)
        if {row.subject_id for row in rows} != registered:
            return _err("report_not_ready", "Approved achievement levels are incomplete for registered learning areas.", 422)
    if not rows:
        return _err("report_not_ready", "No approved levels for this learner yet.", 422)
    if is_cbc_level_stage and len({row.scale_id for row in rows}) != 1:
        return _err("report_not_ready", "This CBC examination contains inconsistent achievement-scale versions.", 422)
    report_scale = rows[0].scale if is_cbc_level_stage else scale
    if is_cbc_level_stage and (report_scale.school_id != student.school_id
                              or not report_scale.covers(exam.class_level)):
        return _err("report_not_ready", "The saved achievement scale does not match this examination grade.", 422)
    school = School.objects.get(pk=user.school_id)
    registrations = list(SubjectRegistration.objects.filter(
        student=student, academic_year=year, subject__school_id=student.school_id,
    ).select_related("subject").order_by("subject__name"))
    combination = [registration.subject.name for registration in registrations]
    from api.report_source import DjangoDataSource
    remarks = DjangoDataSource().get_remarks(str(user.school_id), str(exam.pk), str(student.pk))
    progress = _prior_level_map(student, rows, exam, atype)
    from marian_reports.assembler import published_report_reference, sign
    report_no = published_report_reference(exam.pk, student.admission_number)
    source = {
        "exam": [exam.pk, exam.published_at, exam.framework_key, exam.assessment_type],
        "school": [school.pk, school.name, school.location, school.phone, school.motto],
        "student": [student.pk, student.admission_number, student.first_name, student.last_name],
        "enrollment": [enr.class_level_id, enr.stream_id, enr.pathway_id],
        "year_term": [year.pk, year.name, term.pk, term.name],
        "scale": [report_scale.pk, report_scale.version, report_scale.levels],
        "results": [[row.pk, row.subject_id, row.level_key, row.comment, row.status,
                     row.updated_at] for row in rows],
        "progress": progress,
        "remarks": remarks,
        "combination": combination if is_senior else [],
    }
    source_digest = hashlib.sha256(json.dumps(
        source, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    verification_token = sign(report_no, source_digest)
    pdf = build_pdf(
        school.name,
        (student.first_name + " " + student.last_name).strip(), student.admission_number,
        enr.class_level.name + " / " + enr.stream.name,
        year.name, term.name, atype, report_scale.levels, rows,
        is_primary=is_primary, is_junior=is_junior, is_senior=is_senior,
        learner_id=student.pk, pathway=enr.pathway.name if is_senior and enr.pathway else "",
        combination=combination if is_senior else (), progress=progress, remarks=remarks,
        address=school.location, phone=school.phone, motto=school.motto,
        report_no=report_no, verification_token=verification_token)
    from api.published_reports import archive_published_report
    artifact = archive_published_report(
        exam=exam, student=student, report_no=report_no,
        result_mode="achievement_levels", pdf=pdf, source_digest=source_digest)
    if artifact is not None:
        return response_for_published_report(request, artifact)
    resp = HttpResponse(pdf, content_type="application/pdf")
    kind = "attachment" if request.query_params.get("download") == "1" else "inline"
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", report_no) + ".pdf"
    resp["Content-Disposition"] = kind + '; filename="' + name + '"'
    resp["Cache-Control"] = "private, no-store"
    resp["X-Report-Reference"] = report_no
    return resp


def level_selection(request, svc, user, exam_id, cn, stream, ids):
    """Readiness for a class that uses level wording, else None."""
    exam = _exam_for(user, exam_id)
    if exam is None:
        return None
    svc.authorize_class(user, cn)
    is_cbc_level_stage = exam.framework_key in CBC_REPORT_FRAMEWORKS
    exact = (svc.ds.list_exam_students(user.school_id, exam.id, cn)
             if is_cbc_level_stage and hasattr(svc.ds, "list_exam_students") else None)
    pool = list(exact if exact is not None else
                svc.ds.list_students(user.school_id, class_name=cn, stream=stream or None))
    if stream:
        pool = [s for s in pool if s.stream == stream]
    if ids:
        keep = {str(i) for i in ids}
        pool = [s for s in pool if str(s.id) in keep]
    if not pool:
        return None
    first = Student.objects.filter(pk=_pk(pool[0].id), school_id=user.school_id).first()
    if first is None:
        return None
    enr, scale = _level_scale(exam, first)
    if scale is None:
        return None
    atype = request.query_params.get("type", exam.assessment_type)
    if atype not in ATYPES:
        return _err("report_not_ready", "Unknown assessment type.", 400)
    pks = [p for p in (_pk(s.id) for s in pool) if p is not None]
    have = set(LevelResult.objects.filter(
        academic_year=exam.term.academic_year, term=exam.term, assessment_type=atype,
        status__in=PRINTABLE, student_id__in=pks).values_list("student_id", flat=True))
    out = {"selected": len(pool), "eligible": 0, "complete": 0, "pending": 0,
           "excluded": [], "published": exam.status == "published", "level_based": True,
           "cohort_ids": [str(s.id) for s in pool],
           "population": cn + (" " + stream if stream else "") + " - " + str(getattr(exam, "name", ""))}
    registered_by_student = {}
    completed_by_student = {}
    if is_cbc_level_stage:
        registered_by_student = {sid: set() for sid in pks}
        for sid, subject_id in SubjectRegistration.objects.filter(
            student_id__in=pks, academic_year=exam.term.academic_year,
            subject__school_id=user.school_id,
        ).values_list("student_id", "subject_id"):
            registered_by_student.setdefault(sid, set()).add(subject_id)
        registered_subject_ids = {subject_id for values in registered_by_student.values()
                                  for subject_id in values}
        if registered_subject_ids and Performance.objects.filter(
            student_id__in=pks, subject_id__in=registered_subject_ids,
            term=exam.term, assessment_type=atype,
        ).exists():
            return None
        for sid, subject_id in LevelResult.objects.filter(
            student_id__in=pks, academic_year=exam.term.academic_year,
            term=exam.term, assessment_type=atype, status__in=PRINTABLE,
        ).values_list("student_id", "subject_id"):
            completed_by_student.setdefault(sid, set()).add(subject_id)
    for s in pool:
        if getattr(s, "status", "active") == "withdrawn":
            out["excluded"].append({"student_id": s.id, "adm_no": s.adm_no,
                                    "reason": "Learner has withdrawn.", "code": "withdrawn"})
        elif is_cbc_level_stage and registered_by_student.get(_pk(s.id)) and registered_by_student[_pk(s.id)].issubset(completed_by_student.get(_pk(s.id), set())):
            out["eligible"] += 1
            out["complete"] += 1
        elif is_cbc_level_stage:
            missing = len(registered_by_student.get(_pk(s.id), set()) - completed_by_student.get(_pk(s.id), set()))
            out["excluded"].append({"student_id": s.id, "adm_no": s.adm_no,
                                    "reason": (f"{missing} registered learning area(s) do not have approved levels yet."
                                               if registered_by_student.get(_pk(s.id)) else "No registered learning areas."),
                                    "code": "incomplete"})
            out["pending"] += 1
        elif _pk(s.id) in have:
            out["eligible"] += 1
            out["complete"] += 1
        else:
            out["excluded"].append({"student_id": s.id, "adm_no": s.adm_no,
                                    "reason": "No approved levels entered yet.", "code": "incomplete"})
            out["pending"] += 1
    out["reports_expected"] = out["eligible"]
    return Response(out)
