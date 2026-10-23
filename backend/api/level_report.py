"""Level-based report card for the level grades: no marks, percentages,
grades or ranks. Only approved or locked levels are printed.
Level wording is set by the school, not official."""
import io
import re

from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from rest_framework.response import Response

from api.level_rules import _enrollment, scale_for
from schools.models import Exam, LevelResult, School, Student

PRINTABLE = ("approved", "locked")
ATYPES = {"opener": "Opener", "mid": "Mid-term", "end": "End-term"}
W, H = A4
M = 28.0
FONT, BOLD = "Helvetica", "Helvetica-Bold"
C1, C2, C3 = M, M + 150, M + 270


def _safe(s):
    return str(s or "").encode("cp1252", "replace").decode("cp1252")


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
        status__in=PRINTABLE).select_related("subject").order_by("subject__name"))


def build_pdf(school_name, learner, adm, class_name, year_name, term_name, atype, levels, rows):
    labels = {x.get("key"): x.get("label", x.get("key")) for x in levels}
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    def footer():
        c.setFont(FONT, 7.5)
        c.drawString(M, M + 14, "Level wording is set by your school, not official.")
        c.drawString(M, M + 4, "This stage reports levels only: no marks, percentages, grades or positions.")

    def head(y):
        c.setLineWidth(0.8)
        c.line(M, y + 12, W - M, y + 12)
        c.setFont(BOLD, 9)
        c.drawString(C1, y, "Subject")
        c.drawString(C2, y, "Level")
        c.drawString(C3, y, "Comment")
        c.line(M, y - 6, W - M, y - 6)
        return y - 20

    y = H - M - 14
    c.setFont(BOLD, 16)
    c.drawString(M, y, _safe(school_name))
    y -= 20
    c.setFont(BOLD, 11)
    c.drawString(M, y, "LEARNING PROGRESS REPORT")
    c.setFont(FONT, 9.5)
    for line in (
        "Learner: " + learner + "     Adm: " + adm,
        "Class: " + class_name,
        "Year: " + year_name + "     Term: " + term_name + "     Assessment: " + ATYPES.get(atype, atype),
    ):
        y -= 15
        c.drawString(M, y, _safe(line))
    y = head(y - 28)
    cw = W - M - C3
    for r in rows:
        lines = simpleSplit(_safe(r.comment), FONT, 8.5, cw) or [""]
        need = max(18, 11 * len(lines) + 7)
        if y - need < M + 36:
            footer()
            c.showPage()
            y = head(H - M - 10)
        c.setFont(FONT, 9)
        c.drawString(C1, y, _safe(r.subject.name)[:34])
        c.setFont(BOLD, 9)
        c.drawString(C2, y, _safe(labels.get(r.level_key, r.level_key))[:28])
        c.setFont(FONT, 8.5)
        for i, ln in enumerate(lines):
            c.drawString(C3, y - 11 * i, ln)
        y -= need
        c.setLineWidth(0.3)
        c.line(M, y + 8, W - M, y + 8)
    footer()
    c.save()
    return buf.getvalue()


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


def level_pdf_response(request, user, st):
    """PDF for one learner if the class uses level wording, else None."""
    exam = _exam_for(user, request.query_params.get("exam_id", ""))
    student = Student.objects.filter(pk=_pk(st.id), school_id=user.school_id).first()
    if exam is None or student is None:
        return None
    enr, scale = _level_scale(exam, student)
    if scale is None:
        return None
    if exam.status != "published":
        return _err("report_not_ready", "This exam is not published yet.", 422)
    atype = request.query_params.get("type", "end")
    if atype not in ATYPES:
        return _err("report_not_ready", "Unknown assessment type.", 422)
    year, term = exam.term.academic_year, exam.term
    rows = approved_rows(student, year, term, atype)
    if not rows:
        return _err("report_not_ready", "No approved levels for this learner yet.", 422)
    pdf = build_pdf(
        School.objects.get(pk=user.school_id).name,
        (student.first_name + " " + student.last_name).strip(), student.admission_number,
        enr.class_level.name + " " + enr.stream.name, year.name, term.name, atype,
        scale.levels, rows)
    resp = HttpResponse(pdf, content_type="application/pdf")
    kind = "attachment" if request.query_params.get("download") == "1" else "inline"
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(student.admission_number)) + "-levels.pdf"
    resp["Content-Disposition"] = kind + '; filename="' + name + '"'
    resp["Cache-Control"] = "private, no-store"
    return resp


def level_selection(request, svc, user, exam_id, cn, stream, ids):
    """Readiness for a class that uses level wording, else None."""
    exam = _exam_for(user, exam_id)
    if exam is None:
        return None
    svc.authorize_class(user, cn)
    pool = list(svc.ds.list_students(user.school_id, class_name=cn, stream=stream or None))
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
    atype = request.query_params.get("type", "end")
    pks = [p for p in (_pk(s.id) for s in pool) if p is not None]
    have = set(LevelResult.objects.filter(
        academic_year=exam.term.academic_year, term=exam.term, assessment_type=atype,
        status__in=PRINTABLE, student_id__in=pks).values_list("student_id", flat=True))
    out = {"selected": len(pool), "eligible": 0, "complete": 0, "pending": 0,
           "excluded": [], "published": exam.status == "published", "level_based": True,
           "population": cn + (" " + stream if stream else "") + " - " + str(getattr(exam, "name", ""))}
    for s in pool:
        if getattr(s, "status", "active") == "withdrawn":
            out["excluded"].append({"student_id": s.id, "adm_no": s.adm_no,
                                    "reason": "Learner has withdrawn.", "code": "withdrawn"})
        elif _pk(s.id) in have:
            out["eligible"] += 1
            out["complete"] += 1
        else:
            out["excluded"].append({"student_id": s.id, "adm_no": s.adm_no,
                                    "reason": "No approved levels entered yet.", "code": "incomplete"})
            out["pending"] += 1
    out["reports_expected"] = out["eligible"]
    return Response(out)
