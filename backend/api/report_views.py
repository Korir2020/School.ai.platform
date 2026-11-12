"""Report API for the marian_reports module (read-only).

Identity comes from the login only (api/report_access.py).
The school's saved grading scale is required: no scale -> 422.
"""
import os
from decimal import Decimal
from functools import wraps

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .suspension import SchoolNotSuspended
from rest_framework.response import Response

from marian_reports.assembler import ReportService
from marian_reports.config import ReportConfig
from marian_reports.domain import NotFound, PermissionDenied, ReportNotReady
from marian_reports.grading import GradingError
from marian_reports.pdf import report_pdf

from api.report_access import build_report_user
from api.report_source import DjangoConfigStore, DjangoDataSource
from marian_reports.comment_templates import (
    clean_templates, default_templates, level_templates, merge_templates,
    numeric_templates, render_template, stage_for_scale,
)


def _err(code, message, status):
    return Response({"error": code, "message": message}, status=status)


def guard(fn):
    @wraps(fn)
    def inner(request, *a, **kw):
        try:
            return fn(request, *a, **kw)
        except NotFound:
            return _err("not_found", "Not found.", 404)
        except PermissionDenied:
            return _err("forbidden", "You do not have access to this.", 403)
        except ReportNotReady as e:
            return _err(e.code, e.message, 422)
        except GradingError as e:
            return _err("invalid_grading", str(e), 400)
    return inner


def _exam_scheme(school_id, exam_id):
    """Grading scale frozen into the framework version recorded on this exam,
    or None (legacy and untracked exams use the school's scale)."""
    from api.report_source import scheme_from_dict
    from schools.models import Exam, FrameworkVersion
    try:
        pk = int(exam_id)
    except (TypeError, ValueError):
        return None
    exam = Exam.objects.filter(pk=pk, school_id=school_id).first()
    if exam is None or not exam.framework_key or not exam.framework_version:
        return None
    fv = FrameworkVersion.objects.filter(
        school_id=school_id, framework_key=exam.framework_key,
        version=exam.framework_version).first()
    rules = fv.rules if fv is not None and isinstance(fv.rules, dict) else {}
    frozen = rules.get("scheme")
    if not isinstance(frozen, dict):
        return None
    return scheme_from_dict(frozen)


def service(school_id, exam_id=None):
    store = DjangoConfigStore(str(school_id))
    scheme = store.load_scheme()
    cfg = ReportConfig()
    store.apply_to(cfg)
    from schools.models import Exam
    from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS, STAGE_PRESETS
    exam = None
    resolved = None
    try:
        exam = Exam.objects.filter(pk=int(exam_id), school_id=school_id).first()
    except (TypeError, ValueError):
        pass
    if exam is not None:
        if exam.framework_key and exam.framework_version:
            scheme = _exam_scheme(school_id, exam_id) or scheme
        else:
            from api.framework_rules import resolve
            resolved = resolve(exam.school_id, exam.class_level, exam.term.academic_year)
            if resolved is not None and isinstance(resolved.rules, dict):
                frozen = resolved.rules.get("scheme")
                if isinstance(frozen, dict):
                    from api.report_source import scheme_from_dict
                    scheme = scheme_from_dict(frozen)
    framework_key = exam.framework_key if exam and exam.framework_key else (
        resolved.framework_key if resolved is not None else None)
    if scheme is None:
        raise ReportNotReady("no_grading_scale",
                             "This school has not set a grading scale yet.")
    saved_templates = store.saved_comment_templates()
    cfg.comment_templates = numeric_templates(
        scheme, saved_templates.get("grading"))
    if framework_key in CBC_REPORT_FRAMEWORKS:
        # CBC school rankings are opt-in. A saved school preference wins.
        preset = STAGE_PRESETS[framework_key]
        saved = store.saved_sections()
        for key, value in preset.get("sections", {}).items():
            if key not in saved:
                cfg.sections[key] = value
        cfg.labels.update(preset.get("labels", {}))
        stage = {"cbe_primary": "Primary", "cbe_junior_levels": "Junior",
                 "cbe_senior": "Senior"}.get(framework_key, "CBC")
        notice = f"Internal CBC {stage} school assessment; not an official KNEC assessment."
        saved_footer = (store.saved_options().get("footer_note") or "").strip()
        cfg.footer_note = notice if not saved_footer else notice + " " + saved_footer
    return ReportService(DjangoDataSource(), scheme, cfg, framework_key=framework_key)


def report_user(request):
    try:
        user = build_report_user(request.user)
    except PermissionDenied:
        from api.class_teacher_access import class_teacher_user
        user = class_teacher_user(request)
    return user


def ctx(request):
    user = report_user(request)
    return user, service(user.school_id, request.query_params.get("exam_id"))


def verify_base():
    return os.environ.get("MARIAN_VERIFY_BASE") or "http://localhost:8000"


def jsonable(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    return o


def params(request):
    q = request.query_params
    ids = [i for i in q.get("ids", "").split(",") if i]
    return (q.get("exam_id", ""), q.get("class_name", ""),
            q.get("stream") or None, ids)


def selection(user, svc, exam_id, class_name, stream, ids):
    """Resolve a selection against the FULL class snapshot of the user's school."""
    svc.authorize_class(user, class_name)
    snap = svc.snapshot(user, exam_id, class_name)
    pool = [s for s in snap.students.values()
            if not stream or s.stream == stream]
    if ids:
        if any(i not in snap.students for i in ids):
            raise NotFound("student")
        pool = [snap.students[i] for i in ids]
    return snap, sorted(pool, key=lambda s: (s.stream, s.adm_no))


def build_many(user, svc, snap, pool, prov):
    reps, errs = [], {}
    for s in pool:
        try:
            reps.append(svc.build_report(user, snap, s.id, provisional_ok=prov))
        except (ReportNotReady, PermissionDenied) as e:
            errs[s.id] = getattr(e, "message", str(e))
    return reps, errs


# ---------------------------------------------------------------- views
@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_meta(request):
    user, svc = ctx(request)
    ds = svc.ds
    studs = ds.list_students(user.school_id)
    if user.role == "teacher":
        studs = [s for s in studs if "*" in user.class_names or s.class_name in user.class_names]
    elif user.role == "guardian":
        studs = [s for s in studs if s.id in user.student_ids]
    exams = [{"id": e.id, "name": e.name, "published": e.published}
             for e in ds.list_exams(user.school_id)]
    from schools.models import Enrollment, Exam, ExamResult, LevelResult
    from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS
    exam_rows = {row.id: row for row in Exam.objects.filter(
        school_id=user.school_id,
    ).select_related("term").only(
        "id", "framework_key", "status", "term_id", "class_level_id",
        "assessment_type", "term__academic_year_id",
    )}
    numeric_ids = set(ExamResult.objects.filter(
        exam_id__in=exam_rows.keys(),
    ).values_list("exam_id", flat=True).distinct())
    level_exams = [row for row in exam_rows.values()
                   if row.framework_key in CBC_REPORT_FRAMEWORKS and row.status == "published"]
    level_terms = {row.term_id for row in level_exams}
    level_years = {row.term.academic_year_id for row in level_exams}
    level_keys = set(LevelResult.objects.filter(
        student__school_id=user.school_id, status__in=["approved", "locked"],
        term_id__in=level_terms, academic_year_id__in=level_years,
        assessment_type__in={row.assessment_type for row in level_exams},
    ).values_list("student_id", "academic_year_id", "term_id", "assessment_type").distinct())
    enrollments = Enrollment.objects.filter(
        student__school_id=user.school_id, student_id__in={row[0] for row in level_keys},
        academic_year_id__in=level_years, is_active=True,
    ).values_list("student_id", "academic_year_id", "class_level_id")
    class_by_student_year = {(sid, year): class_id for sid, year, class_id in enrollments}
    level_exam_ids_by_scope = {(row.term_id, row.assessment_type, row.class_level_id): row.id
                               for row in level_exams}
    level_exam_ids = set()
    for student_id, year_id, term_id, atype in level_keys:
        class_id = class_by_student_year.get((student_id, year_id))
        exam_id = level_exam_ids_by_scope.get((term_id, atype, class_id))
        if exam_id:
            level_exam_ids.add(exam_id)
    saved_sections = DjangoConfigStore(str(user.school_id)).saved_sections()
    for item in exams:
        try:
            exam_id = int(item["id"])
        except (TypeError, ValueError):
            exam_id = None
        exam = exam_rows.get(exam_id)
        item["framework_key"] = exam.framework_key if exam else None
        item["assessment_type"] = exam.assessment_type if exam else "end"
        item["result_mode"] = ("achievement_levels" if exam and exam.framework_key in CBC_REPORT_FRAMEWORKS
                               and exam.status == "published" and exam_id not in numeric_ids
                               and exam_id in level_exam_ids else "marks")
        item["rankings_enabled"] = (bool(saved_sections.get("positions", False))
                                    if exam and exam.framework_key in CBC_REPORT_FRAMEWORKS else True)
    if user.role == "teacher":
        from api.class_teacher_access import limit_meta
        studs, exams = limit_meta(request.user, studs, exams)
    return Response({
        "role": user.role, "exams": exams,
        "classes": sorted({s.class_name for s in studs}),
        "streams": sorted({s.stream for s in studs}),
        "students": [{"id": s.id, "adm_no": s.adm_no, "name": s.full_name,
                      "class": s.class_name, "stream": s.stream, "status": s.status}
                     for s in studs],
        "config": {"allow_provisional": svc.cfg.allow_provisional,
                   "max_batch": svc.cfg.max_batch}})


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_selection(request):
    user, svc = ctx(request)
    exam_id, cn, stream, ids = params(request)
    if user.role == "teacher":
        from api.class_teacher_access import enforce_selection
        stream, ids = enforce_selection(request, user, exam_id, cn, stream, ids)
    from api.level_report import level_selection
    lv = level_selection(request, svc, user, exam_id, cn, stream, ids)
    if lv is not None:
        return lv
    snap, pool = selection(user, svc, exam_id, cn, stream, ids)
    prov = request.query_params.get("provisional") == "1"
    out = {"selected": len(pool), "eligible": 0, "complete": 0, "pending": 0,
           "excluded": [], "published": snap.exam.published,
           "cohort_ids": [str(s.id) for s in pool],
           "population": f"{cn}{' ' + stream if stream else ''} - {snap.exam.name}"}
    for s in pool:
        try:
            is_prov = svc.check_ready(snap, s, prov)
            out["eligible"] += 1
            out["pending" if is_prov else "complete"] += 1
        except ReportNotReady as e:
            out["excluded"].append({"student_id": s.id, "adm_no": s.adm_no,
                                    "reason": e.message, "code": e.code})
            if e.code == "incomplete":
                out["pending"] += 1
    out["reports_expected"] = out["eligible"]
    return Response(out)


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_student_pdf(request, student_id):
    user = report_user(request)
    from api.report_source import DjangoDataSource
    from marian_reports.assembler import authorize_student
    st = DjangoDataSource().get_student(user.school_id, str(student_id))
    authorize_student(user, st)
    if user.role == "teacher":
        from api.class_teacher_access import enforce_student
        enforce_student(request, user, st)
    exam_id = request.query_params.get("exam_id", "")
    from api.published_reports import find_published_report, response_for_published_report
    try:
        archived = find_published_report(user.school_id, int(exam_id), int(st.id))
    except (TypeError, ValueError):
        archived = None
    if archived is not None:
        return response_for_published_report(request, archived)
    from api.level_report import level_pdf_response
    lv = level_pdf_response(request, user, st)
    if lv is not None:
        return lv
    svc = service(user.school_id, exam_id)
    snap = svc.snapshot(user, exam_id, st.class_name)
    prov = request.query_params.get("provisional") == "1"
    rd = svc.build_report(user, snap, st.id, provisional_ok=prov)
    pdf = report_pdf(rd, verify_base())
    if snap.exam.published and not rd.provisional:
        from schools.models import Exam, Student
        from api.published_reports import archive_published_report
        exam_row = Exam.objects.filter(pk=int(snap.exam.id), school_id=user.school_id).first()
        student_row = Student.objects.filter(pk=int(st.id), school_id=user.school_id).first()
        if exam_row is not None and student_row is not None:
            artifact = archive_published_report(
                exam=exam_row, student=student_row, report_no=rd.report_no,
                result_mode="marks", pdf=pdf, source_digest=rd.snapshot_id)
            if artifact is not None:
                return response_for_published_report(request, artifact)
    resp = HttpResponse(pdf, content_type="application/pdf")
    kind = "attachment" if request.query_params.get("download") == "1" else "inline"
    resp["Content-Disposition"] = f'{kind}; filename="{safe_name(rd.report_no)}.pdf"'
    resp["Cache-Control"] = "private, no-store"
    resp["X-Report-Reference"] = rd.report_no
    return resp


import re

from rest_framework.decorators import authentication_classes
from rest_framework.permissions import AllowAny

from marian_reports import analytics, export
from marian_reports.assembler import sign
from marian_reports.domain import User


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s))[:80] or "report"


def _class_snapshot(request):
    user, svc = ctx(request)
    exam_id, cn, stream, _ids = params(request)
    svc.authorize_class(user, cn)
    return svc, svc.snapshot(user, exam_id, cn), stream


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_analytics(request):
    svc, snap, stream = _class_snapshot(request)
    subject = request.query_params.get("subject")
    data = (analytics.subject_stats(snap, svc.scheme, subject, stream) if subject
            else analytics.group_stats(snap, svc.scheme, stream))
    if not subject and svc.framework_key == "cbe_senior":
        data["pathway_combinations"] = analytics.senior_combination_stats(snap, svc.scheme, stream)
        data["comparison_note"] = (
            "Senior summaries are grouped by pathway and exact registered subject combination; "
            "these are internal school calculations, not official KNEC rankings."
        )
    return Response(jsonable(data))


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_rankings(request):
    svc, snap, stream = _class_snapshot(request)
    from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS
    if svc.framework_key in CBC_REPORT_FRAMEWORKS \
            and not svc.cfg.sections.get("positions", False):
        return _err("rankings_disabled", "CBC rankings are disabled by this school's report policy.", 403)
    scope = request.query_params.get("scope", "overall")
    if scope not in ("overall", "stream"):
        raise ReportNotReady("bad_scope", "scope must be overall or stream.")
    if scope == "stream" and stream not in snap.stream:
        raise NotFound("stream")
    return Response(jsonable(analytics.ranking_table(
        snap, scope, stream, framework_key=svc.framework_key)))


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_support_list(request):
    svc, snap, _stream = _class_snapshot(request)
    return Response(jsonable(analytics.support_list(snap)))


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_export(request, fmt):
    if fmt not in ("csv", "xlsx"):
        raise NotFound("format")
    user, svc = ctx(request)
    exam_id, cn, stream, ids = params(request)
    snap, pool = selection(user, svc, exam_id, cn, stream, ids)
    reps, _errs = build_many(user, svc, snap, pool,
                             request.query_params.get("provisional") == "1")
    data = export.to_csv(reps) if fmt == "csv" else export.to_xlsx(reps)
    mime = ("text/csv" if fmt == "csv" else
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp = HttpResponse(data, content_type=mime)
    resp["Content-Disposition"] = f'attachment; filename="results_{safe_name(snap.exam.id)}.{fmt}"'
    resp["Cache-Control"] = "private, no-store"
    return resp


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def report_verify(request, report_no):
    """Public. Confirms authenticity only; never returns learner details."""
    ok = False
    try:
        sid = request.query_params.get("s", "")
        tok = request.query_params.get("t", "")
        want = request.query_params.get("e", "")
        qualified = re.fullmatch(r"RPT-E([0-9]+)-(.+)", report_no)
        from schools.models import PublishedReportArtifact
        if qualified:
            exam_id, adm = qualified.group(1), qualified.group(2)
            if want and want != exam_id:
                raise ValueError("exam mismatch")
            artifact = PublishedReportArtifact.objects.filter(
                school_id=sid, exam_id=exam_id, report_no=report_no).first()
            if artifact is not None:
                ok = tok == artifact.verification_token
            else:
                svc = service(sid)
                sysu = User("system", sid, "admin")
                stu = next(s for s in svc.ds.list_students(sid) if s.adm_no == adm)
                exam = next((e for e in svc.ds.list_exams(sid)
                             if str(e.id) == exam_id and e.published), None)
                if exam is not None:
                    snap = svc.snapshot(sysu, exam.id, stu.class_name)
                    ok = sign(report_no, snap.snapshot_id) == tok
        else:
            _p, year, term, adm = report_no.split("-", 3)
            year, term = int(year), int(term[1:])
            svc = service(sid)
            sysu = User("system", sid, "admin")
            stu = next(s for s in svc.ds.list_students(sid) if s.adm_no == adm)
            for e in svc.ds.list_exams(sid):
                if want and str(e.id) != want:
                    continue
                if e.year == year and e.term == term:
                    snap = svc.snapshot(sysu, e.id, stu.class_name)
                    if sign(report_no, snap.snapshot_id) == tok:
                        ok = True
                        break
    except Exception:
        ok = False
    if ok:
        return Response({"valid": True, "report_no": report_no})
    return Response({"valid": False}, status=404)


# ------------------------------------------------------------ comments
from marian_reports.comments import AINotConfigured, CommentError, CommentService

from api.report_source import DjangoAuditLog, DjangoCommentStore, DjangoRemarkStore


def comment_service(user, svc):
    """Built per request: durable store + approved-remark store + audit log."""
    try:
        remarks = DjangoRemarkStore()
    except TypeError:
        remarks = DjangoRemarkStore(str(user.school_id))
    return CommentService(
        svc.ds, svc, DjangoAuditLog(), remarks.set_remark, remarks.clear_remark,
        drafter=None, store=DjangoCommentStore(str(user.school_id)))


def comment_call(fn, *args):
    try:
        return Response({"comment": jsonable(fn(*args))})
    except CommentError as e:
        return _err("invalid_comment", str(e), 400)
    except AINotConfigured as e:
        return _err("ai_not_configured", str(e), 501)


def cbody(request):
    b = request.data
    return b if isinstance(b, dict) else {}


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_comments_list(request):
    user, svc = ctx(request)
    cs = comment_service(user, svc)
    q = request.query_params
    exam_id, class_name = q.get("exam_id", ""), q.get("class_name", "")
    rows = cs.listing(user, exam_id, class_name)
    if user.role == "teacher":
        from api.class_teacher_access import enforce_selection
        from schools.models import Enrollment, Exam
        stream, _ids = enforce_selection(request, user, exam_id, class_name,
                                         q.get("stream") or None, [])
        exam = Exam.objects.get(pk=int(exam_id), school_id=user.school_id)
        allowed = set(str(value) for value in Enrollment.objects.filter(
            student__school_id=user.school_id, academic_year_id=exam.term.academic_year_id,
            class_level=exam.class_level, stream__name=stream, is_active=True,
        ).values_list("student_id", flat=True))
        rows = [row for row in rows if row["student_id"] in allowed]
    return Response({"comments": jsonable(
        rows)})


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_comment_defaults(request):
    """Return editable scale-based suggestions only; never persist or print them here."""
    user, svc = ctx(request)
    exam_id = str(request.query_params.get("exam_id", ""))
    student_id = str(request.query_params.get("student_id", ""))
    if not exam_id or not student_id:
        return _err("invalid_comment", "Choose an exam and learner.", 400)
    student = svc.ds.get_student(user.school_id, student_id)
    svc.authorize_student(user, student)
    from schools.models import Exam, ExamResult, LevelResult
    try:
        exam_pk = int(exam_id)
    except (TypeError, ValueError):
        raise NotFound("exam")
    exam = Exam.objects.filter(pk=exam_pk, school_id=user.school_id).select_related(
        "term__academic_year", "class_level").first()
    if exam is None:
        raise NotFound("exam")
    if user.role == "teacher":
        from api.class_teacher_access import enforce_comment
        enforce_comment(request, user, student_id, exam_id)
    atype = request.query_params.get("type", exam.assessment_type)
    if atype not in ("opener", "mid", "end"):
        return _err("invalid_comment", "Unknown assessment type.", 400)
    store = DjangoConfigStore(str(user.school_id))
    saved = store.saved_comment_templates()
    from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS
    if exam.framework_key in CBC_REPORT_FRAMEWORKS and not ExamResult.objects.filter(exam=exam).exists():
        rows = list(LevelResult.objects.filter(
            student_id=student.id, academic_year=exam.term.academic_year,
            term=exam.term, assessment_type=atype, status__in=["approved", "locked"],
        ).select_related("subject", "scale").order_by("subject__name"))
        if rows:
            scale = rows[0].scale
            key = f"level:{scale.pk}"
            templates = level_templates(scale, saved.get(key))
            stage = {"cbe_primary": "Primary", "cbe_junior_levels": "Junior",
                     "cbe_senior": "Senior"}.get(exam.framework_key, "CBC")
            level_labels = {item.get("key"): item.get("label", item.get("key"))
                            for item in scale.levels if isinstance(item, dict)}
            order = [item.get("key") for item in scale.levels if isinstance(item, dict)]
            recorded = []
            subject_suggestions = []
            for row in rows:
                level_label = level_labels.get(row.level_key, row.level_key)
                if row.level_key not in recorded:
                    recorded.append(row.level_key)
                template = templates.get(row.level_key, {}).get("subject", "")
                subject_suggestions.append({
                    "subject": row.subject.name,
                    "text": render_template(template, level=level_label,
                                            subject=row.subject.name,
                                            scale="school-defined achievement scale",
                                            stage=stage),
                })
            recorded_labels = ", ".join(level_labels.get(k, k) for k in order if k in recorded)
            overall = templates.get("__overall__", {})
            return Response({
                "mode": "achievement_levels", "stage": stage,
                "comments": {
                    field: render_template(overall.get(field, ""),
                                           levels=recorded_labels or "the recorded descriptors",
                                           scale="school-defined achievement scale", stage=stage)
                    for field in ("class_teacher", "principal")
                },
                "subject_comments": subject_suggestions,
            })

    snap = svc.snapshot(user, exam_id, student.class_name)
    summary = snap.summaries.get(student.id)
    if summary is None:
        raise ReportNotReady("no_results", "No results are recorded for this learner.")
    level = summary.mean_points_grade or "recorded school result"
    row_templates = svc.cfg.comment_templates.get(level, {})
    comments = {
        field: render_template(row_templates.get(field, ""), level=level,
                              scale="school grading scale", stage="school")
        for field in ("class_teacher", "principal")
    }
    return Response({
        "mode": "marks", "stage": "School",
        "comments": comments,
        "subject_comments": [
            {"subject": row.subject,
             "text": render_template(
                 svc.cfg.comment_templates.get(row.grade or "", {}).get("subject", ""),
                 level=row.grade or "recorded result", subject=row.subject,
                 scale="school grading scale", stage="school")}
            for row in summary.subjects if row.status == "scored"
        ],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_comment_draft(request):
    user, svc = ctx(request)
    b = cbody(request)
    exam_id, student_id = str(b.get("exam_id", "")), str(b.get("student_id", ""))
    if user.role == "teacher":
        from api.class_teacher_access import enforce_comment
        enforce_comment(request, user, student_id, exam_id)
    return comment_call(comment_service(user, svc).draft, user,
                        exam_id, student_id,
                        b.get("field", "class_teacher"), b.get("text"))


def _authorize_comment_scope(request, user, cid):
    if user.role != "teacher":
        return
    from api.class_teacher_access import enforce_comment
    from schools.models import ReportComment
    row = ReportComment.objects.filter(id=cid, school_id=user.school_id).first()
    if row is None:
        raise NotFound("comment")
    enforce_comment(request, user, row.student_id, row.exam_id)


@api_view(["PUT"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_comment_edit(request, cid):
    user, svc = ctx(request)
    _authorize_comment_scope(request, user, cid)
    return comment_call(comment_service(user, svc).edit, user, cid,
                        cbody(request).get("text"))


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_comment_approve(request, cid):
    user, svc = ctx(request)
    _authorize_comment_scope(request, user, cid)
    return comment_call(comment_service(user, svc).approve, user, cid)


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_comment_reject(request, cid):
    user, svc = ctx(request)
    _authorize_comment_scope(request, user, cid)
    return comment_call(comment_service(user, svc).reject, user, cid)


# ------------------------------------------------------- admin settings
from marian_reports.audit import AuditAccessDenied
from marian_reports.grading import make_scheme
from marian_reports.section_setup import SectionError, apply_sections, effective_sections
from api.report_options import OPTION_CHOICES, OptionError, effective_options, validate_options

OPTIONS = {"rounding": ["half_up", "half_even", "down"],
           "mean_rule": ["total_over_max", "average_of_percentages"],
           "absent_policy": ["pending", "zero", "exclude"]}


def admin_user(request):
    user = build_report_user(request.user)
    if user.role != "admin":
        raise PermissionDenied("admin only")
    return user


def scheme_json(s):
    return {"configured": True, "options": OPTIONS,
            "bands": [[b.label, str(b.min_pct), str(b.max_pct), str(b.points)]
                      for b in sorted(s.bands, key=lambda b: b.min_pct)],
            "pass_pct": str(s.pass_pct), "decimals": s.decimals,
            "rounding": s.rounding, "mean_rule": s.mean_rule,
            "absent_policy": s.absent_policy, "best_n": s.best_n}


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_grading_config(request):
    user = admin_user(request)
    store = DjangoConfigStore(str(user.school_id))
    if request.method == "PUT":
        b = cbody(request)
        try:
            bands = b["bands"]
            if not isinstance(bands, list):
                raise TypeError("bands")
            best = b.get("best_n")
            new = make_scheme(
                [tuple(x) for x in bands], pass_pct=b["pass_pct"],
                decimals=int(b.get("decimals", 2)),
                rounding=b.get("rounding", "half_up"),
                mean_rule=b.get("mean_rule", "total_over_max"),
                absent_policy=b.get("absent_policy", "pending"),
                best_n=int(best) if best not in (None, "") else None)
        except (KeyError, TypeError):
            return _err("invalid_grading",
                        'Send {"bands": [[label, from, to, points], ...], "pass_pct": number}.', 400)
        except ValueError as e:      # includes GradingError: overlaps, gaps, bad numbers
            return _err("invalid_grading", str(e), 400)
        store.save_scheme(new)
        DjangoAuditLog().record(user, "grading_scale.changed", "scheme",
                                {"bands": len(new.bands), "pass_pct": str(new.pass_pct), "best_n": new.best_n})
    s = store.load_scheme()
    if s is None:
        return Response({"configured": False, "options": OPTIONS})
    return Response(scheme_json(s))


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_section_config(request):
    user = admin_user(request)
    store = DjangoConfigStore(str(user.school_id))
    cfg = ReportConfig()
    store.apply_to(cfg)
    extra = {}
    if request.method == "PUT":
        try:
            changed = apply_sections(cfg, cbody(request))
        except SectionError as e:
            return _err("invalid_sections", str(e), 400)
        if changed:
            store.save_sections({k: new for k, (_old, new) in changed.items()})
            DjangoAuditLog().record(user, "sections.changed", "sections", {"changed": changed})
        extra["changed"] = changed
    return Response({"sections": effective_sections(cfg), **extra})


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_options(request):
    user = admin_user(request)
    store = DjangoConfigStore(str(user.school_id))
    if request.method == "PUT":
        try:
            clean = validate_options(cbody(request).get("options"))
        except OptionError as e:
            return _err("invalid_options", str(e), 400)
        if clean:
            store.save_options(clean)
            DjangoAuditLog().record(user, "options.changed", "options", {"changed": sorted(clean)})
    cfg = ReportConfig()
    store.apply_to(cfg)
    return Response({"options": effective_options(cfg), "choices": OPTION_CHOICES})


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_audit(request):
    user = admin_user(request)
    q = request.query_params
    try:
        lim = max(1, min(500, int(q.get("limit", 100))))
    except ValueError:
        lim = 100
    try:
        rows = DjangoAuditLog().entries(user, q.get("action") or None, lim)
    except AuditAccessDenied:
        raise PermissionDenied("admin only")
    return Response({"entries": jsonable(rows)})


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_grading_scale(request):
    """Read-only view of the school's saved scale for admins and teachers."""
    from api.report_access import SchoolAdminProfile, TeacherProfile
    prof = (SchoolAdminProfile.objects.filter(user=request.user).first()
            or TeacherProfile.objects.filter(user=request.user).first())
    if prof is None:
        raise PermissionDenied("not allowed")
    s = DjangoConfigStore(str(prof.school_id)).load_scheme()
    if s is None:
        return Response({"configured": False})
    d = scheme_json(s)
    d.pop("options", None)
    return Response(d)


def _comment_scale_catalog(school_id, store):
    """Return the school's current numeric scale and saved CBC level-scale versions."""
    from schools.models import LevelScale
    saved = store.saved_comment_templates()
    scales = []
    scheme = store.load_scheme()
    if scheme is not None:
        labels = [(band.label, band.label)
                  for band in sorted(scheme.bands, key=lambda row: row.min_pct, reverse=True)]
        defaults = default_templates(labels, kind="numeric", scale_name="school grading scale")
        scales.append({
            "key": "grading", "label": "School grading scale", "mode": "marks",
            "entries": [{"key": key, "label": label, "fields": list(defaults[key])}
                        for key, label in labels],
            "templates": merge_templates(defaults, saved.get("grading")),
        })
    for scale in LevelScale.objects.filter(school_id=school_id).order_by(
            "curriculum__name", "min_level", "version"):
        stage = stage_for_scale(scale.min_level, scale.max_level)
        labels = [(item.get("key", ""), item.get("label", item.get("key", "")))
                  for item in scale.levels if isinstance(item, dict) and item.get("key")]
        defaults = default_templates(labels, kind="level", stage=stage)
        curriculum_name = scale.curriculum.name
        label = f"CBC {stage} · {curriculum_name} · Grades {scale.min_level}–{scale.max_level} · v{scale.version}"
        key = f"level:{scale.pk}"
        scales.append({
            "key": key, "label": label, "mode": "achievement_levels", "stage": stage,
            "entries": [
                *[{"key": entry_key, "label": entry_label, "fields": list(defaults[entry_key])}
                  for entry_key, entry_label in labels],
                {"key": "__overall__", "label": "Overall feedback", "fields": list(defaults["__overall__"])},
            ],
            "templates": merge_templates(defaults, saved.get(key)),
        })
    return scales


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@guard
def report_comment_templates(request):
    """Editable defaults; GET is available to assigned school staff, PUT to admins only."""
    if request.method == "PUT":
        user = admin_user(request)
    else:
        user, _svc = ctx(request)
    store = DjangoConfigStore(str(user.school_id))
    scales = _comment_scale_catalog(user.school_id, store)
    if request.method == "GET":
        key = request.query_params.get("scale_key")
        if key:
            scales = [row for row in scales if row["key"] == key]
        return Response({"templates": scales})

    body = cbody(request)
    scale_key = str(body.get("scale_key", ""))
    scale = next((row for row in scales if row["key"] == scale_key), None)
    if scale is None:
        return _err("invalid_comment_templates", "Choose a scale belonging to this school.", 400)
    defaults = default_templates(
        [(entry["key"], entry["label"]) for entry in scale["entries"]
         if entry["key"] != "__overall__"],
        kind="level" if scale["mode"] == "achievement_levels" else "numeric",
        stage=scale.get("stage", "CBC"),
    )
    if scale["mode"] == "achievement_levels":
        defaults["__overall__"] = default_templates(
            [(entry["key"], entry["label"]) for entry in scale["entries"]
             if entry["key"] != "__overall__"], kind="level", stage=scale.get("stage", "CBC"),
        )["__overall__"]
    try:
        cleaned = clean_templates(defaults, body.get("templates"))
    except ValueError as exc:
        return _err("invalid_comment_templates", str(exc), 400)
    saved = store.saved_comment_templates()
    existing = saved.get(scale_key, {}) if isinstance(saved.get(scale_key), dict) else {}
    updated = {key: dict(value) for key, value in existing.items() if isinstance(value, dict)}
    for entry_key, fields in cleaned.items():
        row = dict(updated.get(entry_key, {}))
        for field, text in fields.items():
            if text:
                row[field] = text
            else:
                row.pop(field, None)
        if row:
            updated[entry_key] = row
        else:
            updated.pop(entry_key, None)
    saved[scale_key] = updated
    store.save_comment_templates(saved)
    DjangoAuditLog().record(user, "comment_templates.changed", scale_key,
                            {"entries": len(cleaned)})
    fresh = next(row for row in _comment_scale_catalog(user.school_id, store)
                 if row["key"] == scale_key)
    return Response({"template": fresh})
