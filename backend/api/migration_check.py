"""Check-only endpoint for the Migration Centre. Saves nothing."""
import csv
import io
import json
import re

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from schools.models import ClassLevel, Enrollment, School, Stream, Student

from .migration_rules import FIELD_LABELS, analyse_upload, detect_header_row
from .student_import import _admin
from .views import _scope

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 40
MAX_CELL = 200
MAX_MATRIX_BYTES = 8 * 1024 * 1024

TABLE_EXTENSIONS = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".pdf")
UNSUPPORTED = {
    ".xls": "Old .xls files cannot be read. Open the file and save it as .xlsx or .csv, then try again.",
    ".doc": "Word documents cannot be read. Open the table in Excel, or copy it and paste it here.",
    ".docx": "Word documents cannot be read. Open the table in Excel, or copy it and paste it here.",
    ".ods": "OpenDocument spreadsheets cannot be read. Save the file as .xlsx or .csv, then try again.",
    ".numbers": "Apple Numbers files cannot be read. Export the file as .xlsx or .csv, then try again.",
    ".jpg": "Photos of a register need photo reading, which is off for this school. Type the list, or use an Excel, CSV or typed PDF file.",
    ".jpeg": "Photos of a register need photo reading, which is off for this school. Type the list, or use an Excel, CSV or typed PDF file.",
    ".png": "Photos of a register need photo reading, which is off for this school. Type the list, or use an Excel, CSV or typed PDF file.",
    ".heic": "Photos of a register need photo reading, which is off for this school. Type the list, or use an Excel, CSV or typed PDF file.",
}


class UploadError(Exception):
    pass


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _delimiter(content):
    for line in content.splitlines():
        if line.strip():
            counts = {d: line.count(d) for d in ("\t", ";", ",")}
            best = max(counts, key=counts.get)
            return best if counts[best] else ","
    return ","


def _parse_text(content):
    """Split pasted or uploaded text into rows, whatever the separator."""
    lines = [ln for ln in content.splitlines() if ln.strip() and not re.fullmatch(r"[\s|:+\-=_]+", ln)]
    sample = lines[:6]
    best, top = None, 0
    for d in ("\t", "|", ";", ","):
        count = sum(ln.count(d) for ln in sample)
        if count > top:
            best, top = d, count
    if best is None:
        return [[c.strip() for c in re.split(r"\s{2,}", ln.strip())] for ln in lines]
    if best == "|":
        return [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    return [[c.strip() for c in r] for r in csv.reader(lines, delimiter=best)]


def _trim(rows):
    while rows and not any(rows[-1]):
        rows.pop()
    if len(rows) > MAX_ROWS + 15:
        raise UploadError(f"Too many rows. Upload at most {MAX_ROWS} learners at a time.")
    return rows


def _parse_xlsx(upload):
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(upload.read()), read_only=True, data_only=True)
        rows = []
        sheet = wb.active
        for row in sheet.iter_rows(values_only=True):
            rows.append([_text(c) for c in row])
            if len(rows) > MAX_ROWS + 20:
                break
        wb.close()
    except UploadError:
        raise
    except Exception:
        raise UploadError(
            "This Excel file could not be opened. It may be damaged or password protected. "
            "Open it in Excel, save a copy as .xlsx or .csv, then try again.")
    if not any(any(c for c in row) for row in rows):
        raise UploadError("The first sheet of this workbook is empty. Put the learners on the first sheet and try again.")
    return _trim(rows)


PDF_PAGE_MARK = re.compile(r"^\s*(page\s*)?\d+\s*(of|/)\s*\d+\s*$", re.I)
MAX_PDF_PAGES = 60


def _parse_pdf(upload):
    raw = upload.read()
    if not raw.startswith(b"%PDF"):
        raise UploadError("This does not look like a PDF file.")
    rows, scanned = [], []
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted and not reader.decrypt(""):
            raise UploadError("This PDF is password protected. Remove the password and try again.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise UploadError("This PDF has more than %d pages. Split it and upload it in parts." % MAX_PDF_PAGES)
        for n, page in enumerate(reader.pages, start=1):
            text = page.extract_text(extraction_mode="layout") or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                try:
                    has_picture = len(page.images) > 0
                except Exception:
                    has_picture = True
                if has_picture:
                    scanned.append(n)
                continue
            for ln in lines:
                if not PDF_PAGE_MARK.match(ln):
                    rows.append([c.strip() for c in re.split(r"\t|\s{2,}", ln)])
    except UploadError:
        raise
    except Exception:
        raise UploadError("Could not read this PDF. Save it again, or use an Excel or CSV file.")
    if scanned:
        nums = ", ".join(str(n) for n in scanned)
        label = "Page %s of this PDF is a picture, not typed text," if len(scanned) == 1 else "Pages %s of this PDF are pictures, not typed text,"
        raise UploadError(label % nums + " so it cannot be read. Nothing was skipped. Use an Excel or CSV file, or a typed PDF.")
    if not rows:
        raise UploadError("No typed text was found in this PDF. If the pages are photos, use the photo option instead.")
    head = detect_header_row(rows)
    if head is not None:
        hdr = [c.lower() for c in rows[head]]
        rows = rows[:head + 1] + [r for r in rows[head + 1:] if [c.lower() for c in r] != hdr]
        bad = [i for i in range(head + 1, len(rows)) if len(rows[i]) != len(hdr)]
        if bad:
            shown = "; ".join("line %d: %s" % (i + 1, " | ".join(rows[i])[:50]) for i in bad[:3])
            raise UploadError("Some rows have a different number of columns than the header (" + shown + "). This usually means an empty cell, and a PDF cannot show which column it belonged to. Nothing was added. Fill every cell, or use an Excel or CSV file.")
    return _trim(rows)


def _matrix(raw):
    """Rows sent back by the browser after the first read, so the file is not uploaded twice."""
    if not raw:
        return None
    if len(raw) > MAX_MATRIX_BYTES:
        raise UploadError("This table is too large to keep re-checking. Choose the file again.")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        raise UploadError("The table could not be read. Choose the file again.")
    if not isinstance(data, list) or not all(isinstance(r, list) for r in data):
        raise UploadError("The table could not be read. Choose the file again.")
    if len(data) > MAX_ROWS + 20:
        raise UploadError(f"Too many rows. Upload at most {MAX_ROWS} learners at a time.")
    rows = []
    for row in data:
        if len(row) > MAX_COLUMNS:
            raise UploadError("One row has too many columns. Check the file and try again.")
        rows.append([_text(c)[:MAX_CELL] for c in row])
    return _trim(rows)


def parse_table(upload=None, text="", matrix=None):
    """Read the upload, the pasted text, or the table the browser already has."""
    if matrix:
        rows = _matrix(matrix)
        if rows:
            return rows
    if upload is not None:
        if upload.size > MAX_BYTES:
            raise UploadError("The file must be 5 MB or smaller. Split it into smaller files.")
        name = (getattr(upload, "name", "") or "").lower()
        ext = name[name.rfind("."):] if "." in name else ""
        if ext in (".xlsx", ".xlsm"):
            return _parse_xlsx(upload)
        if ext == ".pdf":
            return _parse_pdf(upload)
        if ext in UNSUPPORTED:
            raise UploadError(UNSUPPORTED[ext])
        if ext and ext not in TABLE_EXTENSIONS:
            raise UploadError(
                f"'{ext}' files cannot be read. Use an Excel (.xlsx), CSV, TSV or typed PDF file, "
                "or copy the table and paste it here.")
        raw = upload.read()
        if b"\x00" in raw[:4096]:
            raise UploadError("This file is not a text table. Use an Excel (.xlsx), CSV, TSV or typed PDF file.")
    else:
        raw = (text or "").encode("utf-8")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252", errors="replace")
    if not content.strip():
        raise UploadError("The file is empty.")
    try:
        rows = [[_text(c) for c in r] for r in _parse_text(content)]
    except csv.Error:
        raise UploadError("Could not read this file as a table.")
    return _trim(rows)


def _confirmations(raw):
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        raise UploadError("The confirmations were not valid.")
    if not isinstance(data, dict):
        raise UploadError("The confirmations were not valid.")
    out = {}
    for key, codes in data.items():
        k = int(key) if str(key).isdigit() else ("all" if key == "all" else None)
        if k is None or not isinstance(codes, list):
            raise UploadError("The confirmations were not valid.")
        out[k] = [str(c) for c in codes]
    return out


FIX_FIELDS = ("first_name", "last_name", "admission_number", "assessment_number", "class_level", "stream")


def _fixes(raw):
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        raise UploadError("The corrections were not valid.")
    if not isinstance(data, dict) or len(data) > MAX_ROWS:
        raise UploadError("The corrections were not valid.")
    out = {}
    for key, fields in data.items():
        if not str(key).isdigit() or not isinstance(fields, dict):
            raise UploadError("The corrections were not valid.")
        clean = {}
        for name, value in fields.items():
            if name not in FIX_FIELDS or not isinstance(value, str) or len(value) > 120:
                raise UploadError("The corrections were not valid.")
            clean[name] = value.strip()
        if clean:
            out[int(key)] = clean
    return out or None


def _mapping(raw):
    """{field: column index} sent by the browser when a heading is not recognised."""
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        raise UploadError("The column choices were not valid.")
    if not isinstance(data, dict):
        raise UploadError("The column choices were not valid.")
    out = {}
    for field, index in data.items():
        if field not in FIELD_LABELS:
            continue
        if index in ("", None):
            continue
        try:
            index = int(index)
        except (TypeError, ValueError):
            raise UploadError("The column choices were not valid.")
        if index < 0 or index >= MAX_COLUMNS:
            raise UploadError("The column choices were not valid.")
        out[field] = index
    return out or None


def _header_row(raw):
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise UploadError("The header row was not valid.")
    if value < -1 or value > 15:
        raise UploadError("The header row was not valid.")
    return value


def build_structure(school_id):
    """Every class the school can use, with the streams it has set up.

    Classes are shared across the platform (the Students page offers the whole
    catalogue), so a class must not vanish from an import just because nothing
    has been enrolled in it yet and it has no streams.
    """
    levels = {}
    streams = Stream.objects.filter(school_id=school_id, is_active=True, class_level__is_active=True).select_related("class_level")
    for s in streams:
        cl = s.class_level
        entry = levels.setdefault(cl.id, {"id": cl.id, "name": cl.name, "level_number": cl.level_number, "streams": []})
        entry["streams"].append({"id": s.id, "name": s.name})
    enrolled = (Enrollment.objects
                .filter(student__school_id=school_id, is_active=True, class_level__is_active=True)
                .values("class_level_id", "class_level__name", "class_level__level_number").distinct())
    for e in enrolled:
        levels.setdefault(e["class_level_id"], {"id": e["class_level_id"], "name": e["class_level__name"],
                                                "level_number": e["class_level__level_number"], "streams": []})
    for cl in ClassLevel.objects.filter(is_active=True).values("id", "name", "level_number"):
        levels.setdefault(cl["id"], {"id": cl["id"], "name": cl["name"],
                                     "level_number": cl["level_number"], "streams": []})
    return sorted(levels.values(), key=lambda x: (x["level_number"], x["name"]))


def build_existing(school_id):
    rows = Student.objects.filter(school_id=school_id).values("id", "first_name", "last_name", "admission_number", "assessment_number")
    return [{**r, "upi": ""} for r in rows]


def read_request(request):
    """Shared by check and commit so both read the upload the same way."""
    upload = request.FILES.get("file")
    text = request.data.get("text", "")
    matrix = request.data.get("matrix")
    if upload is None and not str(text).strip() and not matrix:
        raise UploadError("Attach a file or paste the table.")
    source = request.data.get("source", "digital")
    if source not in ("digital", "paper"):
        raise UploadError("Unknown source.")
    rows = parse_table(upload, text, matrix)
    if not rows:
        raise UploadError("No rows were found in this file.")
    return {
        "matrix": rows,
        "source": source,
        "upload": upload,
        "confirmations": _confirmations(request.data.get("confirmations")),
        "fixes": _fixes(request.data.get("fixes")),
        "mapping": _mapping(request.data.get("mapping")),
        "header_row": _header_row(request.data.get("header_row")),
        "default_class": str(request.data.get("default_class") or "").strip(),
        "name_order": request.data.get("name_order") or None,
    }


@extend_schema(request=OpenApiTypes.OBJECT, responses={
    200: OpenApiResponse(description="Review table. Nothing is saved."),
    400: OpenApiResponse(description="The file could not be read."),
    403: OpenApiResponse(description="Administrator authorization required.")})
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def migration_check(request):
    school_id, error = _scope(request)
    if error:
        return error
    if not _admin(request.user):
        return Response({"detail": "Only school administrators can check an upload."}, status=403)
    if school_id is None:
        raw = request.data.get("school_id")
        if not str(raw or "").isdigit() or not School.objects.filter(pk=int(raw)).exists():
            return Response({"detail": "Choose a school."}, status=400)
        school_id = int(raw)
    try:
        data = read_request(request)
    except UploadError as exc:
        return Response({"detail": str(exc)}, status=400)
    result = analyse_upload(
        data["matrix"], build_structure(school_id), existing=build_existing(school_id),
        source=data["source"], name_order=data["name_order"],
        default_class=data["default_class"], confirmations=data["confirmations"],
        fixes=data["fixes"], mapping=data["mapping"], header_row=data["header_row"])
    result["committed"] = False
    result["matrix"] = data["matrix"]
    result["source"] = data["source"]
    return Response(result)
