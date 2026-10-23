"""Check-only endpoint for the Migration Centre. Saves nothing."""
import csv
import io
import json

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from schools.models import Enrollment, School, Stream, Student

from .migration_rules import analyse_upload
from .student_import import _admin
from .views import _scope

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000


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
        for row in wb.active.iter_rows(values_only=True):
            rows.append([_text(c) for c in row])
            if len(rows) > MAX_ROWS + 20:
                break
        wb.close()
    except Exception:
        raise UploadError("Could not read this Excel file. Save it again as .xlsx or .csv.")
    return _trim(rows)


def parse_table(upload=None, text=""):
    if upload is not None:
        if upload.size > MAX_BYTES:
            raise UploadError("The file must be 5 MB or smaller.")
        name = (getattr(upload, "name", "") or "").lower()
        if name.endswith(".xlsx"):
            return _parse_xlsx(upload)
        if name.endswith(".xls"):
            raise UploadError("Old .xls files are not supported. Save as .xlsx or .csv and try again.")
        raw = upload.read()
    else:
        raw = (text or "").encode("utf-8")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252", errors="replace")
    if not content.strip():
        raise UploadError("The file is empty.")
    try:
        rows = [[_text(c) for c in r] for r in csv.reader(io.StringIO(content), delimiter=_delimiter(content))]
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


def build_structure(school_id):
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
    return sorted(levels.values(), key=lambda x: (x["level_number"], x["name"]))


def build_existing(school_id):
    rows = Student.objects.filter(school_id=school_id).values("id", "first_name", "last_name", "admission_number")
    return [{**r, "assessment_number": "", "upi": ""} for r in rows]


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
    upload = request.FILES.get("file")
    text = request.data.get("text", "")
    if upload is None and not str(text).strip():
        return Response({"detail": "Attach a file or paste the table."}, status=400)
    source = request.data.get("source", "digital")
    if source not in ("digital", "paper"):
        return Response({"detail": "Unknown source."}, status=400)
    try:
        matrix = parse_table(upload, text)
        confirmations = _confirmations(request.data.get("confirmations"))
    except UploadError as exc:
        return Response({"detail": str(exc)}, status=400)
    result = analyse_upload(
        matrix, build_structure(school_id), existing=build_existing(school_id), source=source,
        name_order=request.data.get("name_order") or None,
        default_class=str(request.data.get("default_class") or ""),
        confirmations=confirmations)
    result["committed"] = False
    return Response(result)
