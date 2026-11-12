"""Stage-specific, school-internal achievement-level report layouts."""
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

W, H = A4
M = 30
CW = W - 2 * M
FONT, BOLD, ITAL = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
INK, MID, LINE, PAPER = (HexColor(value) for value in
                         ("#17232e", "#586775", "#d5dee5", "#f5f8fa"))
PROFILES = {
    "primary": {"title": "PRIMARY LEARNING JOURNEY", "range": "GRADES 1–6",
                 "accent": HexColor("#18776f"), "soft": HexColor("#e8f5f2"),
                 "area": "Learning area", "progress": "Prior record"},
    "junior": {"title": "JUNIOR LEARNING PROFILE", "range": "GRADES 7–9",
               "accent": HexColor("#3c5e9b"), "soft": HexColor("#edf1fa"),
               "area": "Learning area", "progress": "Previous descriptor"},
    "senior": {"title": "SENIOR PATHWAY PROGRESS", "range": "GRADES 10–12",
               "accent": HexColor("#8c4b67"), "soft": HexColor("#f8eef2"),
               "area": "Registered subject", "progress": "Previous descriptor"},
}


def _safe(value):
    return ("" if value is None else str(value)).encode("cp1252", "replace").decode("cp1252")


def _text(c, x, top, text, *, font=FONT, size=8, color=INK, width=None, align="left"):
    text = _safe(text)
    if width is not None:
        while size > 5.5 and c.stringWidth(text, font, size) > width:
            size -= .25
        if c.stringWidth(text, font, size) > width:
            while text and c.stringWidth(text + "...", font, size) > width:
                text = text[:-1]
            text += "..."
    c.setFont(font, size)
    c.setFillColor(color)
    y = H - top
    if align == "right":
        c.drawRightString(x, y, text)
    elif align == "center":
        c.drawCentredString(x, y, text)
    else:
        c.drawString(x, y, text)


def _paragraph(c, x, top, width, text, *, font=FONT, size=7.3, color=INK, max_lines=None, leading=None):
    leading = leading or size * 1.24
    lines = simpleSplit(_safe(text), font, size, width) or [""]
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


def _profile(stage):
    return PROFILES.get(stage, PROFILES["primary"])


def _header(c, school_name, profile, page, pages, address="", phone="", motto=""):
    c.setFillColor(profile["accent"])
    c.rect(0, H - 84, W, 84, fill=1, stroke=0)
    _text(c, M, 25, school_name, font=BOLD, size=15, color=white, width=CW - 8)
    _text(c, M, 45, profile["title"], font=BOLD, size=10.5, color=white, width=CW - 8)
    _text(c, M, 62, "CBC " + profile["range"] + " · ACHIEVEMENT-LEVEL REPORT", font=BOLD, size=7.4, color=white)
    _text(c, M, 77, "INTERNAL SCHOOL ASSESSMENT · NOT AN OFFICIAL KNEC REPORT OR TEMPLATE", font=BOLD, size=6.5, color=white)
    _text(c, W - M, 77, f"{page}/{pages}", font=BOLD, size=6.7, color=white, align="right")
    contact = " · ".join(value for value in (address, phone) if value)
    if contact:
        _text(c, W - M, 25, contact, size=7, color=white, width=220, align="right")
    if motto:
        _text(c, W - M, 44, motto, font=ITAL, size=7, color=white, width=220, align="right")


def _row_layout(row, levels, progress, stage):
    current = next((item for item in levels if item.get("key") == row.level_key), {})
    labels = [item.get("label", item.get("key", "")) for item in levels]
    keys = [item.get("key") for item in levels]
    try:
        position = keys.index(row.level_key)
    except ValueError:
        position = -1
    if position >= 0 and position + 1 < len(levels):
        next_step = (f"Possible next step: work toward {labels[position + 1]} through a "
                     "teacher-selected learning activity.")
    else:
        next_step = "Possible extension: apply the recorded descriptor in a new teacher-selected task."
    teacher_note = (row.comment or "").strip()
    descriptor = str(current.get("description", "")).strip()
    level_text = str(current.get("label", row.level_key))
    if descriptor:
        level_text += "\n" + descriptor
    feedback = teacher_note or "Teacher feedback not recorded."
    return {
        "subject": row.subject.name,
        "level": level_text,
        "feedback": feedback,
        "progress": progress.get(getattr(row, "subject_id", None),
                                 "First approved record in this report history."),
        "next": next_step,
    }


def _draw_identity(c, top, learner, adm, learner_id, class_name, year_name, term_name,
                   assessment, profile, report_no="", pathway="", combination=()):
    senior = profile is PROFILES["senior"]
    height = 134 if senior else 100
    c.setFillColor(PAPER)
    c.setStrokeColor(LINE)
    c.roundRect(M, H - top - height, CW, height, 7, fill=1, stroke=1)
    _text(c, M + 12, top + 18, learner, font=BOLD, size=13, width=CW - 24)
    fields = [
        ("ADMISSION NO.", adm), ("CLASS / STREAM", class_name),
        ("ASSESSMENT", f"{assessment} · {term_name} {year_name}"),
        ("SCHOOL YEAR", year_name),
        ("REPORT REFERENCE", report_no),
    ]
    if senior:
        fields.extend([("PATHWAY", pathway or "Not recorded"),
                       ("REGISTERED COMBINATION", ", ".join(combination) or "Not recorded")])
    colw = (CW - 24) / 2
    for index, (label, value) in enumerate(fields):
        col, row = index % 2, index // 2
        x = M + 12 + col * colw
        y = top + 37 + row * 23
        _text(c, x, y, label, font=BOLD, size=6.2, color=MID)
        _text(c, x, y + 10, value, font=BOLD, size=8, width=colw - 10)
    return top + height


def _draw_level_distribution(c, top, profile, rows, levels):
    counts = {item.get("key"): 0 for item in levels}
    for row in rows:
        counts[row.level_key] = counts.get(row.level_key, 0) + 1
    parts = [f"{item.get('label', item.get('key'))}: {counts.get(item.get('key'), 0)}"
             for item in levels if counts.get(item.get("key"), 0)]
    text = "Recorded descriptor counts: " + (" · ".join(parts) if parts else "No descriptor counts")
    height = 36
    c.setFillColor(profile["soft"])
    c.setStrokeColor(profile["accent"])
    c.roundRect(M, H - top - height, CW, height, 6, fill=1, stroke=1)
    _text(c, M + 10, top + 13, "SCHOOL-DEFINED ACHIEVEMENT PROFILE", font=BOLD, size=7, color=profile["accent"])
    _paragraph(c, M + 10, top + 18, CW - 20, text, size=7.3, max_lines=2)
    return top + height


def _header_row(c, profile, top, widths):
    c.setFillColor(profile["accent"])
    c.roundRect(M, H - top - 24, CW, 24, 5, fill=1, stroke=0)
    labels = [profile["area"], "CURRENT SCHOOL LEVEL", profile["progress"], "TEACHER FEEDBACK", "POSSIBLE NEXT STEP"]
    x = M
    for width, label in zip(widths, labels):
        _text(c, x + 6, top + 15, label, font=BOLD, size=6.1, color=white, width=width - 10)
        x += width


def _row_height(row, widths):
    columns = ((row["subject"], BOLD, 7.3), (row["level"], BOLD, 7.2),
               (row["progress"], FONT, 6.8), (row["feedback"], FONT, 7.0),
               (row["next"], FONT, 6.8))
    return max(34, min(82, 13 + max(len(simpleSplit(_safe(text), font, size, widths[index] - 12))
                                         for index, (text, font, size) in enumerate(columns)) * 8.5))


def _draw_rows(c, rows, top, widths, start=0):
    xpositions = [M]
    for width in widths:
        xpositions.append(xpositions[-1] + width)
    y = top
    for index, row in enumerate(rows, start):
        height = _row_height(row, widths)
        if index % 2 == 0:
            c.setFillColor(PAPER)
            c.rect(M, H - y - height, CW, height, fill=1, stroke=0)
        c.setStrokeColor(LINE)
        c.setLineWidth(.4)
        c.line(M, H - y - height, M + CW, H - y - height)
        cells = [(row["subject"], BOLD, 7.3), (row["level"], BOLD, 7.2),
                 (row["progress"], FONT, 6.8), (row["feedback"], FONT, 7.0),
                 (row["next"], FONT, 6.8)]
        for col, (text, font, size) in enumerate(cells):
            _paragraph(c, xpositions[col] + 6, y + 6, widths[col] - 12, text,
                       font=font, size=size, max_lines=max(2, int((height - 8) / 8)))
        y += height
    return y


def _comment_boxes(c, profile, top, remarks):
    labels = (("class_teacher", "CLASS-TEACHER COMMENT"), ("principal", "HEADTEACHER / PRINCIPAL COMMENT"))
    width = (CW - 10) / 2
    heights = []
    for index, (key, label) in enumerate(labels):
        text = remarks.get(key, "")
        body = text or "No approved comment recorded."
        lines = simpleSplit(_safe(body), FONT, 7.2, width - 14)
        height = max(44, 24 + min(len(lines), 4) * 8.5)
        x = M + index * (width + 10)
        c.setFillColor(PAPER)
        c.setStrokeColor(LINE)
        c.roundRect(x, H - top - height, width, height, 6, fill=1, stroke=1)
        _text(c, x + 7, top + 12, label, font=BOLD, size=6.3, color=profile["accent"])
        _paragraph(c, x + 7, top + 16, width - 14, body, size=7.2, max_lines=4,
                   color=INK if text else MID)
        heights.append(height)
    return max(heights)


def render_level_report(*, school_name, learner, adm, learner_id, class_name, year_name,
                        term_name, assessment, stage, levels, rows, progress=None,
                        remarks=None, address="", phone="", motto="", pathway="",
                        combination=(), report_no="", verification_token=""):
    if stage not in PROFILES:
        stage = "primary"
    profile = PROFILES[stage]
    progress = progress or {}
    remarks = remarks or {}
    row_data = [_row_layout(row, levels, progress, stage) for row in rows]
    widths = [112, 95, 86, 134, CW - 112 - 95 - 86 - 134]
    first_id_height = 134 if stage == "senior" else 100
    table_top = 95 + first_id_height + 12 + 36 + 13 + 24 + 5
    first_capacity = H - table_top - 175
    continuation_top = 147
    continuation_capacity = H - continuation_top - 175
    chunks, chunk, used = [], [], 0
    capacity = first_capacity
    for item in row_data:
        height = _row_height(item, widths)
        if chunk and used + height > capacity:
            chunks.append(chunk)
            chunk, used, capacity = [], 0, continuation_capacity
        chunk.append(item)
        used += height
    if chunk:
        chunks.append(chunk)
    if not chunks:
        chunks = [[]]

    buf = __import__("io").BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
    c.setTitle(f"CBC {profile['title']} — {report_no or adm}")
    for page_index, items in enumerate(chunks):
        _header(c, school_name, profile, page_index + 1, len(chunks), address, phone, motto)
        if page_index == 0:
            cursor = _draw_identity(c, 95, learner, adm, learner_id, class_name,
                                    year_name, term_name, assessment, profile,
                                    report_no, pathway, combination) + 12
            cursor = _draw_level_distribution(c, cursor, profile, rows, levels) + 13
            _text(c, M, cursor + 10, "LEARNING EVIDENCE & TEACHER-GUIDED NEXT STEPS",
                  font=BOLD, size=7.2, color=profile["accent"])
            cursor += 16
        else:
            c.setFillColor(PAPER)
            c.setStrokeColor(LINE)
            c.roundRect(M, H - 95 - 34, CW, 34, 5, fill=1, stroke=1)
            _text(c, M + 8, 108, learner, font=BOLD, size=9)
            _text(c, W - M - 8, 108, f"{class_name} · {term_name} {year_name}",
                  size=7, color=MID, width=220, align="right")
            cursor = continuation_top - 24
        _header_row(c, profile, cursor, widths)
        row_top = cursor + 24
        row_end = _draw_rows(c, items, row_top, widths,
                             sum(len(part) for part in chunks[:page_index]))
        if page_index == len(chunks) - 1:
            comment_top = row_end + 12
            if comment_top + 55 < H - 28:
                _comment_boxes(c, profile, comment_top, remarks)
            else:
                c.showPage()
                _header(c, school_name, profile, len(chunks) + 1, len(chunks) + 1,
                        address, phone, motto)
                _comment_boxes(c, profile, 105, remarks)
        c.setStrokeColor(LINE)
        c.setLineWidth(.5)
        c.line(M, 30, W - M, 30)
        _text(c, M, H - 16,
              "INTERNAL SCHOOL ASSESSMENT · School-authored levels; not an official KNEC report or template.",
              font=BOLD, size=6.1, color=MID, width=CW)
        _text(c, W - M, H - 16, f"{adm} · {term_name} {year_name}",
              size=6.1, color=MID, align="right")
        if report_no:
            _text(c, W - M, H - 40, f"{report_no} · VERIFY {verification_token}",
                  font=BOLD, size=6.1, color=MID, width=CW, align="right")
        c.showPage()
    c.save()
    return buf.getvalue()
