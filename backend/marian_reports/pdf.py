"""ReportLab renderer: one A4 page per student, drawn at fixed positions so page breaks are exact.
Monochrome palette so it stays readable in grayscale. Displays ReportData; never recomputes it."""
from __future__ import annotations
import io, os
from decimal import Decimal
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from .assembler import ReportData
from .domain import ReportNotReady

W, H = A4
M = 28.0
CW = W - 2 * M
INK, MID, LIGHT, LINE, ZEBRA, DARK = (HexColor(x) for x in ("#1f1f1f", "#5a5a5a", "#efefef", "#9a9a9a", "#f5f5f5", "#2b2b2b"))
MAX_SUBJECTS = 14
FONT, BOLD, ITAL = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def safe(s) -> str:
    # Standard PDF fonts use WinAnsi (cp1252): supports en/em dashes, middle dot, accents.
    return ("" if s is None else str(s)).encode("cp1252", "replace").decode("cp1252")


def fmt(d) -> str:
    if d is None: return "—"
    d = Decimal(d)
    s = format(d.normalize(), "f") if d == d.to_integral() else format(d.normalize(), "f")
    return s


def _fit(c, s, font, size, maxw, min_size=5.5):
    s = safe(s)
    while size > min_size and c.stringWidth(s, font, size) > maxw: size -= 0.25
    if c.stringWidth(s, font, size) > maxw:
        while s and c.stringWidth(s + "...", font, size) > maxw: s = s[:-1]
        s += "..."
    return s, size


def txt(c, x, t, s, font=FONT, size=8, color=INK, align="l", maxw=None):
    if maxw: s, size = _fit(c, s, font, size, maxw)
    else: s = safe(s)
    c.setFillColor(color); c.setFont(font, size)
    y = H - t
    {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[align](x, y, s)


def rbox(c, x, t, w, h, r=5, fill=None, stroke=INK, lw=0.9, dash=None):
    c.saveState(); c.setLineWidth(lw)
    if dash: c.setDash(*dash)
    if fill is not None: c.setFillColor(fill)
    if stroke is not None: c.setStrokeColor(stroke)
    c.roundRect(x, H - t - h, w, h, r, stroke=1 if stroke is not None else 0, fill=1 if fill is not None else 0)
    c.restoreState()


def para(c, x, t, w, h, s, font=FONT, size=9, color=INK, leading=1.2, min_size=5.5):
    """Wrap s inside w x h (top-left origin); shrink, then ellipsize, so nothing is clipped."""
    s = safe(s)
    while True:
        lines = simpleSplit(s, font, size, w)
        if len(lines) * size * leading <= h or size <= min_size: break
        size -= 0.5
    maxl = max(1, int(h // (size * leading)))
    if len(lines) > maxl:
        lines = lines[:maxl]; last = lines[-1]
        while last and c.stringWidth(last + "...", font, size) > w: last = last[:-1]
        lines[-1] = last + "..."
    c.setFillColor(color); c.setFont(font, size)
    for i, ln in enumerate(lines):
        c.drawString(x, H - t - size - i * size * leading, ln)


def pill(c, cx, t_mid, s, size=7.5, fill=DARK, color=white):
    s = safe(s); w = c.stringWidth(s, BOLD, size) + 8
    rbox(c, cx - w / 2, t_mid - 6, w, 12, 3, fill=fill, stroke=None)
    txt(c, cx, t_mid + 2.6, s, BOLD, size, color, "c")


def monogram(c, x, t, size, text):
    rbox(c, x, t, size, size, 4, fill=DARK, stroke=DARK)
    txt(c, x + size / 2, t + size * 0.62, text, BOLD, size * 0.4, white, "c")


def _logo(c, school, x, t, size):
    if school.logo_path and os.path.exists(school.logo_path):
        try:
            c.drawImage(school.logo_path, x, H - t - size, size, size, preserveAspectRatio=True, mask="auto")
            return
        except Exception:
            pass
    monogram(c, x, t, size, "".join(w[0] for w in school.name.split()[:2]).upper())


def validate_for_render(rd: ReportData):
    if len(rd.subjects) > MAX_SUBJECTS:
        raise ReportNotReady("too_many_subjects", f"{len(rd.subjects)} subjects exceed the one-page limit of {MAX_SUBJECTS}.")
    if not rd.subjects:
        raise ReportNotReady("no_subjects", "No subjects to print.")


def draw_report(c: canvas.Canvas, rd: ReportData, page_no: int = 1, page_total: int = 1, verify_base: str = "http://localhost:5000"):
    validate_for_render(rd)
    sec, sch, st, ex = rd.sections, rd.school, rd.student, rd.exam
    term_title = f"STUDENT PROGRESS REPORT — TERM {ex.term}, {ex.year}"
    if rd.provisional or not ex.published:
        c.saveState(); c.setFillColor(black); c.setFillAlpha(0.07); c.setFont(BOLD, 86)
        c.translate(W / 2, H / 2); c.rotate(52)
        c.drawCentredString(0, 0, "PROVISIONAL" if rd.provisional else "DRAFT"); c.restoreState()
    # ---- header
    _logo(c, sch, M, 26, 54); _logo(c, sch, W - M - 54, 26, 54)
    txt(c, W / 2, 36, "STUDENT PROGRESS REPORT", FONT, 8.5, MID, "c")
    txt(c, W / 2, 58, sch.name, BOLD, 20, INK, "c", maxw=CW - 130)
    if sch.motto: txt(c, W / 2, 70, f"“{sch.motto}”".replace("“", '"').replace("”", '"'), ITAL, 8.5, MID, "c", maxw=CW - 130)
    txt(c, W / 2, 81, f"{sch.address}  {sch.phone}".strip(), FONT, 8.5, INK, "c", maxw=CW - 130)
    c.setStrokeColor(INK); c.setLineWidth(1.6); c.line(M, H - 92, W - M, H - 92)
    rbox(c, M, 98, CW, 24, 6, fill=DARK, stroke=DARK)
    tt_ = safe(term_title); cs = 1.2
    tw = c.stringWidth(tt_, BOLD, 11.5) + cs * len(tt_)
    c.saveState()
    to = c.beginText(W / 2 - tw / 2, H - 114); to.setFont(BOLD, 11.5); to.setCharSpace(cs); to.setFillColor(white)
    to.textOut(tt_); c.drawText(to)
    c.restoreState()
    pw = min(CW - 40, 150 + c.stringWidth(safe(ex.name), BOLD, 8))
    rbox(c, W / 2 - pw / 2, 127, pw, 17, 4, stroke=INK, lw=0.9)
    txt(c, W / 2, 138.5, f"Exam: {ex.name}", BOLD, 8.5, INK, "c", maxw=pw - 10)
    if rd.provisional:
        rbox(c, W - M - 120, 127, 120, 17, 4, fill=DARK, stroke=DARK)
        txt(c, W - M - 60, 138.5, "PROVISIONAL REPORT", BOLD, 7.5, white, "c")
    elif not ex.published:
        rbox(c, W - M - 120, 127, 120, 17, 4, fill=DARK, stroke=DARK)
        txt(c, W - M - 60, 138.5, "DRAFT - UNPUBLISHED", BOLD, 7.5, white, "c")
    # ---- student card
    top = 152; ch = 86; lw_ = 325
    rbox(c, M, top, lw_, ch, 7)
    initials = "".join(p[0] for p in st.full_name.split()[:2]).upper() or "?"
    monogram(c, M + 10, top + 12, 52, initials)
    txt(c, M + 74, top + 20, st.full_name.upper(), BOLD, 12, INK, maxw=lw_ - 84)
    fields = [("ADM NO", st.adm_no), ("CLASS", f"{st.class_name} {st.stream}".strip())]
    if sec.get("kcpe", True) and st.kcpe_score: fields.append(("KCPE SCORE", str(st.kcpe_score)))
    if sec.get("gender", True) and st.gender: fields.append(("GENDER", st.gender))
    fields.append(("REPORT NO", rd.report_no))
    for i, (k, v) in enumerate(fields[:6]):
        col, row = i % 2, i // 2
        fx, fy = M + 74 + col * 118, top + 36 + row * 16
        txt(c, fx, fy, k, BOLD, 6.2, MID); txt(c, fx, fy + 8.5, v, BOLD, 8.5, INK, maxw=112)
    # chart
    cx0, cw_ = M + lw_ + 12, CW - lw_ - 12
    rbox(c, cx0, top, cw_, ch, 7)
    if sec.get("performance_chart", True):
        txt(c, cx0 + 10, top + 14, "PERFORMANCE OVER TIME", BOLD, 7, INK)
        px0, px1, pt0, pt1 = cx0 + 24, cx0 + cw_ - 14, top + 22, top + ch - 18
        c.setStrokeColor(LINE); c.setLineWidth(0.4)
        for pts, lab in _ticks(rd):
            y = pt1 - (pts / _scale_max(rd)) * (pt1 - pt0)
            c.line(px0, H - y, px1, H - y); txt(c, px0 - 5, y + 2.2, lab, BOLD, 6.5, MID, "r")
        hist = rd.history; n = len(hist); coords = []
        for i, h in enumerate(hist):
            x = px0 + 12 + (px1 - px0 - 24) * (i / (n - 1) if n > 1 else 0.5)
            txt(c, x, top + ch - 7, h["exam"], FONT, 5.8, MID, "c")
            if h["mean"] is not None:
                coords.append((x, pt1 - (float(h["mean"]) / _scale_max(rd)) * (pt1 - pt0)))
        c.setStrokeColor(INK); c.setLineWidth(1.1)
        for (xa, ya), (xb, yb) in zip(coords, coords[1:]): c.line(xa, H - ya, xb, H - yb)
        c.setFillColor(INK)
        for x, y in coords: c.circle(x, H - y, 2.1, stroke=0, fill=1)
        if not coords: txt(c, cx0 + cw_ / 2, top + 45, "No history yet", ITAL, 7, MID, "c")
    # ---- KPI row
    kt, kh = 246, 38
    kp = [("MEAN", f"{fmt(rd.mean_points)} ({rd.mean_grade})" if rd.mean_points is not None else "—"),
          ("TOTAL MARKS", f"{fmt(rd.total)}/{fmt(rd.max_total)}"),
          ("TOTAL POINTS", f"{fmt(rd.best_points)}/{fmt(rd.max_points)}"),
          ("STREAM POS", rd.positions["stream"]["label"])]
    if not sec.get("aggregate", True):
        kp = [x for x in kp if x[0] not in ("MEAN", "TOTAL POINTS")]
    if sec.get("gender_position", True): kp.append(("GENDER POS", rd.positions["gender"]["label"]))
    kp.append(("OVERALL POS", rd.positions["overall"]["label"]))
    if not sec.get("positions", True):
        kp = [x for x in kp if "POS" not in x[0]]
    gap = 6; bw = (CW - gap * (len(kp) - 1)) / len(kp)
    for i, (k, v) in enumerate(kp):
        x = M + i * (bw + gap); last = i == len(kp) - 1
        rbox(c, x, kt, bw, kh, 6, fill=DARK if last else None, stroke=INK)
        col = white if last else INK
        txt(c, x + bw / 2, kt + 13, k, BOLD, 6.5, col, "c"); txt(c, x + bw / 2, kt + 29, v, BOLD, 12.5, col, "c", maxw=bw - 8)
    txt(c, M, kt + kh + 10, (rd.rank_note if sec.get("positions", True) else ""), FONT, 7, INK, maxw=250)
    txt(c, W - M, kt + kh + 10, f"{rd.completed} subjects completed · {rd.pending} pending" + (f" · {rd.excluded} exempt" if rd.excluded else ""),
        FONT, 7, MID, "r")
    # ---- bottom block heights (fixed) -> table gets the rest
    show_att = bool(sec.get("attendance", False) and rd.attendance)
    show_bd = bool(sec.get("assessment_breakdown", False) and rd.breakdown_summary)
    EXTRA = 24 if (show_att or show_bd) else 0
    BOTTOM = 54 + 106 + 92 + 36 + 80 + 28 + EXTRA
    tt = kt + kh + 18; th = 20
    avail = H - tt - BOTTOM - th - 8
    n = len(rd.subjects); rh = max(8.0, min(20.0, avail / n)); fs = 8.5 if rh >= 15 else 7 if rh >= 11 else 6.2
    if n * rh > avail + 0.01:
        raise ReportNotReady("too_many_subjects",
                             f"{n} subjects do not fit on one page" + (" with the attendance/assessment strip; "
                             "turn that section off or reduce subjects." if EXTRA else "."))
    cols = [M, M + 150, M + 190, M + 226, M + 270, M + 310, M + 358, M + 436, M + CW]
    show_pos = sec.get("subject_position", True)
    if not show_pos:
        cols[6] = cols[5]
    rbox(c, M, tt, CW, th, 5, fill=DARK, stroke=DARK)
    heads = [((rd.labels or {}).get("subject", "SUBJECT"), "l"), ("SCORE", "c"), ("MAX", "c"), ("GRADE", "c"), ("POINTS", "c"), ("POS", "c"), ("REMARK", "l"), ("TEACHER", "l")]
    for i, (h_, al) in enumerate(heads):
        x = cols[i] + 8 if al == "l" else (cols[i] + cols[i + 1]) / 2
        txt(c, x, tt + 13.5, "" if (h_ == "POS" and not show_pos) else h_, BOLD, 7.2, white, al)
    y = tt + th
    for i, ln in enumerate(rd.subjects):
        if i % 2 == 0: c.setFillColor(ZEBRA); c.rect(M, H - y - rh, CW, rh, stroke=0, fill=1)
        c.setStrokeColor(LINE); c.setLineWidth(0.4); c.line(M, H - y - rh, M + CW, H - y - rh)
        mid = y + rh / 2 + fs * 0.35
        txt(c, cols[0] + 8, mid, ln.subject, BOLD, fs, INK, maxw=cols[1] - cols[0] - 12)
        if ln.status == "scored":
            txt(c, (cols[1] + cols[2]) / 2, mid, fmt(ln.score), BOLD, fs + 0.5, INK, "c")
            pill(c, (cols[3] + cols[4]) / 2, y + rh / 2, ln.grade, fs - 0.5)
            txt(c, (cols[4] + cols[5]) / 2, mid, fmt(ln.points), FONT, fs, INK, "c")
        else:   # a missing mark is never shown as 0
            txt(c, (cols[1] + cols[2]) / 2, mid, "—", BOLD, fs, MID, "c")
            txt(c, (cols[3] + cols[4]) / 2, mid, ln.grade, ITAL, fs - 0.5, MID, "c", maxw=cols[4] - cols[3] - 2)
            txt(c, (cols[4] + cols[5]) / 2, mid, "—", FONT, fs, MID, "c")
        txt(c, (cols[2] + cols[3]) / 2, mid, fmt(ln.max_mark), FONT, fs - 0.5, MID, "c")
        if show_pos:
            txt(c, (cols[5] + cols[6]) / 2, mid, ln.position or "—", FONT, fs - 0.5, INK, "c", maxw=cols[6] - cols[5] - 2)
        txt(c, cols[6] + 6, mid, ln.remark, BOLD, fs - 0.5, INK, maxw=cols[7] - cols[6] - 8)
        txt(c, cols[7] + 6, mid, ln.teacher, FONT, fs - 0.5, INK, maxw=cols[8] - cols[7] - 8)
        y += rh
    # ---- lower blocks are anchored to the page bottom so layout is identical for every student
    y = H - BOTTOM
    # ---- attendance | assessment breakdown (optional one-line strip; drawn only when data exists)
    if EXTRA:
        both = show_att and show_bd
        aw = 292 if both else CW; bx = M + aw + 8; bw_ = CW - aw - 8
        if show_att:
            a = rd.attendance
            rbox(c, M, y, aw, 18, 5); txt(c, M + 8, y + 12, "ATTENDANCE", BOLD, 6.6, INK)
            txt(c, M + 62, y + 12, f"Present {a['present']} of {a['open']} days ({fmt(a['pct'])}%) · Absent {a['absent']} · Late {a['late']}",
                FONT, 7.4, INK, maxw=aw - 70)
        if show_bd:
            x_, w_ = (bx, bw_) if both else (M, CW)
            rbox(c, x_, y, w_, 18, 5); txt(c, x_ + 8, y + 12, "ASSESSMENT", BOLD, 6.6, INK)
            line = "   ".join(f"{b['name']}: " + (f"{fmt(b['avg_pct'])}%" if b['avg_pct'] is not None else "—") for b in rd.breakdown_summary)
            txt(c, x_ + 58, y + 12, line, FONT, 7.4, INK, maxw=w_ - 66)
        y += EXTRA
    # ---- insight
    if sec.get("insight", True):
        rbox(c, M, y, CW, 46, 6)
        txt(c, M + 10, y + 12, "PERFORMANCE INSIGHT", BOLD, 7, INK)
        txt(c, M + 112, y + 12, "(calculated from the marks above; advice is rule-based)", ITAL, 6, MID)
        body = " ".join(rd.insight["facts"] + ([rd.insight["recommendation"]] if rd.insight["recommendation"] else []))
        para(c, M + 10, y + 17, CW - 20, 26, body or "No insight available until results are complete.", FONT, 7.8)
    y += 54
    # ---- progress history | remarks
    lw2 = 250; rx = M + lw2 + 14; rw = CW - lw2 - 14
    if sec.get("history", True):
        txt(c, M, y + 9, "PROGRESS HISTORY", BOLD, 8.5, INK); c.setFillColor(INK); c.rect(M - 6, H - y - 12, 2.5, 12, stroke=0, fill=1)
        ht = y + 16; hist = rd.history[-4:]
        rbox(c, M, ht, lw2, 18, 4, fill=DARK, stroke=DARK)
        colw = (lw2 - 70) / max(1, len(hist))
        txt(c, M + 8, ht + 12.5, "EXAM", BOLD, 7, white)
        for i, h in enumerate(hist):
            txt(c, M + 70 + colw * (i + .5), ht + 12.5, h["exam"], BOLD, 6.8, white, "c", maxw=colw - 2)
        for r_, (lab, key) in enumerate((("Mean", "mean"), ("Grade", "grade"))):
            ry = ht + 18 + r_ * 18
            c.setStrokeColor(LINE); c.setLineWidth(0.4); c.line(M, H - ry - 18, M + lw2, H - ry - 18)
            txt(c, M + 8, ry + 12, lab, FONT, 8, INK)
            for i, h in enumerate(hist):
                v = h[key]; cxm = M + 70 + colw * (i + .5)
                if key == "mean": txt(c, cxm, ry + 12, fmt(v) if v is not None else "-", BOLD, 8.5, INK, "c")
                elif v and v != "—": pill(c, cxm, ry + 9, v, 7)
                else: txt(c, cxm, ry + 12, "-", BOLD, 8.5, MID, "c")
    for i, (key, label, flag) in enumerate((("class_teacher", "CLASS TEACHER'S REMARK:", "class_teacher_remark"),
                                          ("principal", "PRINCIPAL'S REMARK:", "principal_remark"))):
        if not sec.get(flag, True): continue
        by = y + i * 50
        rbox(c, rx, by, rw, 44, 6); txt(c, rx + 9, by + 11, label, BOLD, 6.8, INK)
        para(c, rx + 9, by + 15, rw - 18, 26, rd.remarks.get(key) or "(not yet entered)", FONT if rd.remarks.get(key) else ITAL, 9.5,
             INK if rd.remarks.get(key) else MID)
    y += 106
    # ---- dates / fees | QR
    if sec.get("school_dates", True):
        rbox(c, M, y, lw2, 50, 6); txt(c, M + 9, y + 12, "SCHOOL DATES", BOLD, 7.5, INK)
        for j, (k, v) in enumerate((("CLOSING", rd.dates["closing"]), ("NEXT TERM OPENS", rd.dates["next_term"]))):
            txt(c, M + 9, y + 26 + j * 12, k, FONT, 7, INK); txt(c, M + lw2 - 9, y + 26 + j * 12, v or "—", BOLD, 8, INK, "r")
    if sec.get("fees", False) and rd.fee_note is not None:
        rbox(c, M, y + 56, lw2, 28, 6); txt(c, M + 9, y + 68, "FEES", BOLD, 7.5, INK)
        txt(c, M + 9, y + 79, rd.fee_note, FONT, 7.5, INK, maxw=lw2 - 18)
    if sec.get("qr", True):
        rbox(c, rx, y, rw, 84, 6)
        qr = QrCodeWidget(f"{verify_base}/verify/{rd.report_no}?s={rd.school.id}&t={rd.token}"); b = qr.getBounds()
        d = Drawing(66, 66, transform=[66 / (b[2] - b[0]), 0, 0, 66 / (b[3] - b[1]), 0, 0]); d.add(qr)
        renderPDF.draw(d, c, rx + 9, H - y - 75)
        txt(c, rx + 86, y + 30, "Verify this report", BOLD, 10, INK)
        para(c, rx + 86, y + 36, rw - 94, 40, "Scan to confirm this report is genuine and unaltered. The code is tied to this exam snapshot.", FONT, 7.8, INK)
    y += 92
    # ---- grading key
    if sec.get("grading_key", True):
        txt(c, M, y + 9, "GRADING KEY", BOLD, 8, INK); c.setFillColor(INK); c.rect(M - 6, H - y - 12, 2.5, 12, stroke=0, fill=1)
        pw_ = (CW - 2 * len(rd.grading_key)) / len(rd.grading_key)
        for i, (g, rng) in enumerate(rd.grading_key):
            x = M + i * (pw_ + 2)
            rbox(c, x, y + 15, pw_, 14, 3, lw=0.6)
            txt(c, x + pw_ / 2, y + 24.6, f"{g} {rng}", BOLD, 5.9, INK, "c", maxw=pw_ - 2)
    y += 36
    # ---- signatures
    if sec.get("signatures", True):
        base = y + 38
        c.setStrokeColor(INK); c.setLineWidth(0.7)
        for x0, x1, lab in ((M, M + 150, "CLASS TEACHER"), (M + 168, M + 330, "PRINCIPAL")):
            c.line(x0, H - base, x1, H - base); txt(c, (x0 + x1) / 2, base + 11, lab, BOLD, 7.5, INK, "c")
        if sch.principal_name: txt(c, M + 249, base + 20, sch.principal_name, FONT, 6.5, MID, "c", maxw=150)
        if sec.get("stamp", True):
            rbox(c, M + 350, y - 2, CW - 350, 46, 4, stroke=MID, lw=0.7, dash=(3, 2))
            txt(c, M + 350 + (CW - 350) / 2, y + 40, "SCHOOL STAMP", BOLD, 6.5, MID, "c")
        pb = y + 62
        c.line(M, H - pb, M + 330, H - pb)
        txt(c, M + 165, pb + 9, "PARENT / GUARDIAN ACKNOWLEDGMENT", BOLD, 6.5, INK, "c")
        txt(c, M + 350, pb, "DATE: ......................................", FONT, 7.5, INK)
    # footer
    c.setStrokeColor(LINE); c.setLineWidth(0.5); c.line(M, 30, W - M, 30)
    txt(c, M, H - 20, f"{sch.name} — {sch.address} — Printed {rd.generated_on} — {rd.report_no}", FONT, 6.8, MID, maxw=CW - 50)
    txt(c, W - M, H - 20, f"{page_no}/{page_total}", FONT, 6.8, MID, "r")
    txt(c, M, H - 11, rd.footer_note, ITAL, 6.8, INK, maxw=CW)
    c.showPage()


def _new(buf, title):
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
    c.setTitle(title); c.setAuthor("Marian Analytics"); return c


def _scale_max(rd):
    return float((getattr(rd, "scale", None) or {}).get("max") or 12)


def _ticks(rd):
    return (getattr(rd, "scale", None) or {}).get("ticks") or ((12, "A"), (9, "B"), (6, "C"), (3, "D"), (1, "E"))


def report_pdf(rd: ReportData, verify_base="http://localhost:5000") -> bytes:
    validate_for_render(rd)
    buf = io.BytesIO(); c = _new(buf, f"Report {rd.report_no}")
    draw_report(c, rd, 1, 1, verify_base); c.save()
    return buf.getvalue()


def combined_pdf(reports: list, title="Report Cards", verify_base="http://localhost:5000") -> bytes:
    """One page per student, in order. Validates every report first so a failure never yields a partial 'success'."""
    for rd in reports: validate_for_render(rd)
    buf = io.BytesIO(); c = _new(buf, title)
    for i, rd in enumerate(reports, 1): draw_report(c, rd, i, len(reports), verify_base)
    c.save()
    return buf.getvalue()
