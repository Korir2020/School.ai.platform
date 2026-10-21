from __future__ import annotations
import csv, io
from openpyxl import Workbook

HEAD = ["Report No", "Adm No", "Name", "Class", "Stream", "Total", "Max", "Best Points", "Max Points", "Mean Points",
        "Mean Grade", "Stream Pos", "Overall Pos", "Completed", "Pending", "Provisional"]


def _safe_cell(v):
    """Neutralise spreadsheet formula injection from names/remarks."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") and not s.replace(".", "", 1).lstrip("-").isdigit() else s


def row(rd):
    return [rd.report_no, rd.student.adm_no, rd.student.full_name, rd.student.class_name, rd.student.stream, rd.total, rd.max_total,
            rd.best_points, rd.max_points, rd.mean_points, rd.mean_grade, rd.positions["stream"]["label"],
            rd.positions["overall"]["label"], rd.completed, rd.pending, "yes" if rd.provisional else "no"]


def to_csv(reports) -> bytes:
    b = io.StringIO(); w = csv.writer(b); w.writerow(HEAD)
    for rd in reports: w.writerow([_safe_cell(v) for v in row(rd)])
    return b.getvalue().encode("utf-8-sig")


def to_xlsx(reports) -> bytes:
    wb = Workbook(); ws = wb.active; ws.title = "Results"; ws.append(HEAD)
    for rd in reports: ws.append([_safe_cell(v) if not isinstance(v, (int, float)) and not hasattr(v, "quantize") else
                                 (float(v) if hasattr(v, "quantize") else v) for v in row(rd)])
    b = io.BytesIO(); wb.save(b); return b.getvalue()
