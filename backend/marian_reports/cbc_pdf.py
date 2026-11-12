"""Dedicated, school-internal CBC numerical report cards by stage.

This renderer is intentionally separate from the legacy 8-4-4 layout. It
prints recorded school data only and never presents a Marian report as a KNEC
result or template.
"""
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

from .domain import ReportNotReady

W, H = A4
M = 30
CW = W - 2 * M
FONT, BOLD, ITAL = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
INK = HexColor("#17232e")
MID = HexColor("#586775")
LINE = HexColor("#d5dee5")
PAPER = HexColor("#f5f8fa")
WHITE = white

STAGES = {
    "cbe_primary": {
        "name": "CBC PRIMARY", "range": "GRADES 1–6",
        "title": "LEARNING AREA PROGRESS REPORT",
        "progress": "RECORDED LEARNING PROGRESS", "table": "LEARNING AREA RECORD",
        "accent": HexColor("#18776f"), "soft": HexColor("#e8f5f2"),
        "area": "Learning area", "grade": "School level", "feedback": "Subject feedback",
    },
    "cbe_junior_levels": {
        "name": "CBC JUNIOR", "range": "GRADES 7–9",
        "title": "LEARNING PROFILE REPORT",
        "progress": "RECORDED LEARNING PROGRESS", "table": "LEARNING AREA RECORD",
        "accent": HexColor("#3c5e9b"), "soft": HexColor("#edf1fa"),
        "area": "Learning area", "grade": "School level", "feedback": "Teacher feedback",
    },
    "cbe_senior": {
        "name": "CBC SENIOR", "range": "GRADES 10–12",
        "title": "PATHWAY & SUBJECT PROGRESS REPORT",
        "progress": "RECORDED SUBJECT PROGRESS", "table": "REGISTERED SUBJECT RECORD",
        "accent": HexColor("#8c4b67"), "soft": HexColor("#f8eef2"),
        "area": "Registered subject", "grade": "School grade", "feedback": "Subject feedback",
    },
}


def _safe(value):
    return ("" if value is None else str(value)).encode("cp1252", "replace").decode("cp1252")


def _fit(c, value, font, size, width, minimum=5.5):
    text = _safe(value)
    while size > minimum and c.stringWidth(text, font, size) > width:
        size -= .25
    if c.stringWidth(text, font, size) > width:
        while text and c.stringWidth(text + "...", font, size) > width:
            text = text[:-1]
        text += "..."
    return text, size


def _text(c, x, top, value, font=FONT, size=8, color=INK, width=None, align="left"):
    value = _safe(value)
    if width is not None:
        value, size = _fit(c, value, font, size, width)
    c.setFillColor(color)
    c.setFont(font, size)
    y = H - top
    if align == "center":
        c.drawCentredString(x, y, value)
    elif align == "right":
        c.drawRightString(x, y, value)
    else:
        c.drawString(x, y, value)


def _paragraph(c, x, top, width, text, *, font=FONT, size=7.4, color=INK, leading=None, max_lines=None):
    text = _safe(text)
    leading = leading or size * 1.25
    lines = simpleSplit(text, font, size, width) or [""]
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and c.stringWidth(last + "...", font, size) > width:
            last = last[:-1]
        lines[-1] = last + "..."
    c.setFont(font, size)
    c.setFillColor(color)
    for index, line in enumerate(lines):
        c.drawString(x, H - top - size - index * leading, line)
    return len(lines) * leading


def _stage(rd):
    return STAGES.get(getattr(rd.exam, "framework_key", None), STAGES["cbe_primary"])


def _internal_note(rd):
    note = (rd.footer_note or "").strip()
    if "internal" not in note.lower():
        note = "INTERNAL SCHOOL ASSESSMENT — not an official KNEC result or template."
    return note


def _page_header(c, rd, stage, page_no, page_total):
    c.setFillColor(stage["accent"])
    c.rect(0, H - 82, W, 82, fill=1, stroke=0)
    _text(c, M, 24, rd.school.name, BOLD, 15, WHITE, width=CW - 8)
    _text(c, M, 43, stage["name"] + " · " + stage["range"], BOLD, 8.5, WHITE)
    _text(c, M, 59, stage["title"], BOLD, 11, WHITE, width=CW - 12)
    _text(c, M, 75, "INTERNAL SCHOOL REPORT · NOT AN OFFICIAL KNEC FORMAT", BOLD, 7, WHITE)
    _text(c, W - M, 75, f"{page_no}/{page_total}", BOLD, 7, WHITE, align="right")
    contact = " · ".join(x for x in (rd.school.address, rd.school.phone) if x)
    if contact:
        _text(c, W - M, 24, contact, FONT, 7, WHITE, width=230, align="right")
    if rd.school.motto:
        _text(c, W - M, 43, rd.school.motto, ITAL, 7.2, WHITE, width=230, align="right")


def _identity(c, rd, stage, top):
    senior = getattr(rd.exam, "framework_key", None) == "cbe_senior"
    height = 102 if senior else 77
    c.setFillColor(PAPER)
    c.setStrokeColor(LINE)
    c.roundRect(M, H - top - height, CW, height, 7, fill=1, stroke=1)
    _text(c, M + 12, top + 17, rd.student.full_name, BOLD, 13, INK, width=CW - 24)
    fields = [
        ("ADMISSION NO.", rd.student.adm_no),
        ("CLASS / STREAM", f"{rd.student.class_name} / {rd.student.stream}".strip(" /")),
        ("ASSESSMENT", f"{rd.exam.name} · {rd.exam.term} {rd.exam.year}"),
        ("REPORT NO.", rd.report_no),
    ]
    if senior:
        fields.extend([
            ("PATHWAY", rd.student.pathway_name or "Not recorded"),
            ("REGISTERED COMBINATION", ", ".join(rd.student.registered_subject_names) or "Not recorded"),
        ])
    cols = 2
    colw = (CW - 24) / cols
    for index, (label, value) in enumerate(fields):
        col, row = index % cols, index // cols
        x = M + 12 + col * colw
        y = top + 35 + row * 23
        _text(c, x, y, label, BOLD, 6.2, MID)
        _text(c, x, y + 10, value, BOLD, 8.3, INK, width=colw - 10)
    return top + height


def _history(c, rd, stage, top):
    height = 46
    c.setFillColor(stage["soft"])
    c.setStrokeColor(stage["accent"])
    c.roundRect(M, H - top - height, CW, height, 6, fill=1, stroke=1)
    _text(c, M + 10, top + 13, stage["progress"], BOLD, 7, stage["accent"])
    entries = rd.history[-4:]
    if not entries:
        _text(c, M + 10, top + 32, "No earlier scored school report is recorded.", ITAL, 7.5, MID)
        return top + height
    gap = 8
    width = (CW - 20 - gap * (len(entries) - 1)) / len(entries)
    for index, row in enumerate(entries):
        x = M + 10 + index * (width + gap)
        result = "—" if row.get("mean") is None else f"{row['mean']} · {row.get('grade') or '—'}"
        _text(c, x, top + 27, row.get("exam", "Assessment"), BOLD, 6.6, MID, width=width)
        _text(c, x, top + 39, result, BOLD, 8, INK, width=width)
    return top + height


def _table_header(c, rd, stage, top):
    c.setFillColor(stage["accent"])
    c.roundRect(M, H - top - 23, CW, 23, 5, fill=1, stroke=0)
    widths = [132, 76, 93, 151, CW - 132 - 76 - 93 - 151]
    labels = [stage["area"], "SCORE / MAX", stage["grade"], stage["feedback"], "SUBJECT TEACHER"]
    x = M
    for width, label in zip(widths, labels):
        _text(c, x + 7, top + 15, label, BOLD, 6.5, WHITE, width=width - 12)
        x += width
    return widths


def _row_height(c, rd, stage, row, widths):
    comment = row.remark if row.status == "scored" else row.grade
    teacher = row.teacher or "—"
    lines = max(
        len(simpleSplit(_safe(row.subject), BOLD, 7.2, widths[0] - 14)),
        len(simpleSplit(_safe(comment), FONT, 7.0, widths[3] - 14)),
        len(simpleSplit(_safe(row.teacher or "—"), FONT, 7.0, widths[4] - 14)),
    )
    return max(32, min(64, 13 + lines * 9))


def _table_rows(c, rd, stage, top, widths, rows, start_index=0):
    y = top
    xpositions = [M]
    for width in widths:
        xpositions.append(xpositions[-1] + width)
    for index, row in enumerate(rows, start_index):
        height = _row_height(c, rd, stage, row, widths)
        if index % 2 == 0:
            c.setFillColor(PAPER)
            c.rect(M, H - y - height, CW, height, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.setLineWidth(.45)
        c.line(M, H - y - height, M + CW, H - y - height)
        comment = row.remark if row.status == "scored" else row.grade
        score = f"{row.score}/{row.max_mark}" if row.status == "scored" else row.grade
        values = [row.subject, score, row.grade, comment, row.teacher or "—"]
        fonts = [BOLD, BOLD, BOLD, FONT, FONT]
        sizes = [7.3, 7.1, 7.1, 7.0, 7.0]
        for col, (value, font, size) in enumerate(zip(values, fonts, sizes)):
            _paragraph(c, xpositions[col] + 7, y + 6, widths[col] - 14, value,
                       font=font, size=size, max_lines=max(2, int((height - 9) / 8)))
        y += height
    return y


def _draw_comment_box(c, stage, top, label, text):
    width = (CW - 9) / 2
    x = M + (width + 9) * (1 if label == "HEADTEACHER / PRINCIPAL" else 0)
    body = text or "No approved comment recorded."
    lines = simpleSplit(_safe(body), FONT, 7.5, width - 16)
    height = max(47, 28 + min(len(lines), 4) * 9)
    c.setFillColor(PAPER)
    c.setStrokeColor(LINE)
    c.roundRect(x, H - top - height, width, height, 6, fill=1, stroke=1)
    _text(c, x + 8, top + 13, label, BOLD, 6.7, stage["accent"])
    _paragraph(c, x + 8, top + 18, width - 16, body, size=7.5, max_lines=4,
               color=INK if text else MID)
    return height


def draw_cbc_numeric(c: canvas.Canvas, rd, verify_base="http://localhost:5000", page_no=1, page_total=1):
    if not rd.subjects:
        raise ReportNotReady("no_subjects", "No subjects to print.")
    stage = _stage(rd)
    total_pages = 1
    # Conservative row-height estimate to reserve space for both approved comment fields.
    widths = [132, 76, 93, 151, CW - 132 - 76 - 93 - 151]
    row_total = sum(_row_height(c, rd, stage, row, widths) for row in rd.subjects)
    first_top = 96 + (102 if stage["name"] == "CBC SENIOR" else 77) + 12 + 46 + 12 + 17 + 23 + 1
    available = H - first_top - 120
    continuation_available = H - (140 + 17 + 23 + 1) - 120
    if row_total > available:
        total_pages = 1
        used = 0
        for row in rd.subjects:
            rh = _row_height(c, rd, stage, row, widths)
            if used + rh > continuation_available:
                total_pages += 1
                used = 0
            used += rh
    chunks = []
    current = []
    used = 0
    cap = available
    for row in rd.subjects:
        rh = _row_height(c, rd, stage, row, widths)
        if current and used + rh > cap:
            chunks.append(current)
            current, used, cap = [], 0, continuation_available
        current.append(row)
        used += rh
    chunks.append(current)
    total_pages = len(chunks)

    for page_index, rows in enumerate(chunks):
        shown_page = page_no + page_index
        _page_header(c, rd, stage, shown_page, page_total if page_total > 1 else total_pages)
        if page_index == 0:
            cursor = _identity(c, rd, stage, 96) + 12
            cursor = _history(c, rd, stage, cursor) + 12
        else:
            c.setFillColor(PAPER)
            c.setStrokeColor(LINE)
            c.roundRect(M, H - 96 - 31, CW, 31, 5, fill=1, stroke=1)
            _text(c, M + 9, 109, rd.student.full_name, BOLD, 10, INK)
            _text(c, W - M - 9, 109,
                  f"{rd.student.class_name} · {rd.exam.name} · {rd.student.adm_no}",
                  FONT, 7, MID, width=250, align="right")
            cursor = 140
        _text(c, M, cursor + 10, stage["table"], BOLD, 7.3, stage["accent"])
        cursor += 17
        widths = _table_header(c, rd, stage, cursor)
        cursor += 23
        row_end = _table_rows(c, rd, stage, cursor + 1, widths, rows,
                              sum(len(chunk) for chunk in chunks[:page_index]))
        if page_index == len(chunks) - 1:
            remarks = rd.remarks or {}
            comments_top = row_end + 12
            if comments_top < H - 120:
                height = _draw_comment_box(c, stage, comments_top, "CLASS TEACHER", remarks.get("class_teacher", ""))
                _draw_comment_box(c, stage, comments_top, "HEADTEACHER / PRINCIPAL", remarks.get("principal", ""))
                comments_bottom = comments_top + height
                qr_top = comments_bottom + 10
                if qr_top + 70 < H - 20:
                    qr = QrCodeWidget(f"{verify_base}/verify/{rd.report_no}?s={rd.school.id}&t={rd.token}&e={rd.exam.id}")
                    bounds = qr.getBounds()
                    drawing = Drawing(44, 44, transform=[44 / (bounds[2] - bounds[0]), 0, 0,
                                                         44 / (bounds[3] - bounds[1]), 0, 0])
                    drawing.add(qr)
                    renderPDF.draw(drawing, c, M, H - qr_top - 44)
                    _text(c, M + 52, qr_top + 12, "Verify published exam record", BOLD, 7.2, INK)
                    _text(c, M + 52, qr_top + 25, "The verification link is tied to this learner and exam.", FONT, 6.8, MID)
        c.setStrokeColor(LINE)
        c.setLineWidth(.5)
        c.line(M, 31, W - M, 31)
        _text(c, M, H - 17, _internal_note(rd), BOLD, 6.2, MID, width=CW)
        _text(c, W - M, H - 17,
              f"{rd.report_no} · {rd.generated_on}", FONT, 6.2, MID, align="right")
        c.showPage()
