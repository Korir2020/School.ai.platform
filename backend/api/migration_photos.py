"""Photo reading for the Migration Centre (one register page per request).

Off until ANTHROPIC_API_KEY is set on the server. A page is either read in full or
the request fails with a clear message. Cells that cannot be read are marked,
never guessed, and the rules block those rows until a person types the value.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import timedelta

from django.db import DatabaseError
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiTypes
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from schools.models import MarkAuditLog, School

from .migration_rules import CHECK_OPEN, UNREADABLE
from .student_import import _admin
from .views import _scope

API_URL = "https://api.anthropic.com/v1/messages"
AUDIT_ACTION = "student_photo_read"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_COLUMNS = 15
MAX_ROWS = 120
SYSTEM = (
    "You transcribe one photographed page of a school class register into a table. "
    "Copy exactly what is written. Never guess, never invent, never correct spelling, never fill a gap. "
    'Reply with JSON only, with no other words, in this shape: {"headers": ["..."], "rows": [["..."]], "notes": ""}. '
    "Give one entry in rows for every learner line on the page, in order, including lines that are hard to read. "
    "Every row must have exactly as many cells as headers. "
    'A cell that is empty on the page is "". '
    'A cell you cannot read at all is "[UNREADABLE]". '
    'A cell you can read but are not sure of is "[CHECK:your best reading]". '
    "Do not turn page titles, totals, signatures or teacher notes into rows. "
    "Describe anything you left out in notes."
)


class PhotoError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def _model():
    return os.environ.get("MIGRATION_PHOTO_MODEL", "").strip() or "claude-sonnet-5-5"


def _daily_cap():
    try:
        return max(1, int(os.environ.get("MIGRATION_PHOTO_PAGES_PER_DAY", "40")))
    except ValueError:
        return 40


def _media_type(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _call_api(body):
    request = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", "x-api-key": _api_key(), "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(request, timeout=100) as response:
        return json.loads(response.read().decode("utf-8"))


def _body(data, media, page, known):
    ask = "This is page %d of the register." % page
    if known:
        ask += " The columns, in order, are: %s. Use exactly these headers." % json.dumps(known)
    else:
        ask += " Copy the column headings exactly as written on the page."
    return {"model": _model(), "max_tokens": 4096, "system": SYSTEM,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media,
                                             "data": base64.b64encode(data).decode("ascii")}},
                {"type": "text", "text": ask}]}]}


def _clean_cell(value):
    text = re.sub(r"[\t\r\n]+", " ", "" if value is None else str(value)).replace('"', "'").strip()
    if re.fullmatch(r"\[\s*unreadable\s*\]", text, re.I):
        return UNREADABLE
    m = re.match(r"\[\s*check\s*:\s*(.*?)\s*\]?$", text, re.I)
    if m:
        guess = m.group(1).strip()
        return (CHECK_OPEN + guess[:100] + "]") if guess else UNREADABLE
    return text[:120]


def _headers(raw):
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        raise PhotoError("The column headings sent with this page were not valid.")
    if not isinstance(data, list) or not data or len(data) > MAX_COLUMNS or not all(isinstance(h, str) for h in data):
        raise PhotoError("The column headings sent with this page were not valid.")
    return [_clean_cell(h) for h in data]


def parse_page(data, page, known_headers=None):
    """Turn the service reply into rows. Anything unclear is refused, never dropped."""
    if data.get("stop_reason") == "max_tokens":
        raise PhotoError("Page %d has too many lines to read in one go. Photograph the top and bottom halves as two pages. Nothing was skipped." % page)
    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    unclear = "Page %d could not be read cleanly. Retake the photo in better light and try again. Nothing was skipped." % page
    try:
        parsed = json.loads(text)
    except ValueError:
        raise PhotoError(unclear)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("rows"), list):
        raise PhotoError(unclear)
    headers = known_headers or [_clean_cell(h) for h in (parsed.get("headers") or []) if isinstance(h, (str, int, float))]
    if not headers or len(headers) > MAX_COLUMNS:
        raise PhotoError("Page %d has no readable column headings. Photograph the page with the headings visible." % page)
    rows = parsed["rows"]
    if not rows:
        raise PhotoError("No learner lines were found on page %d. Retake the photo so the whole table is visible." % page)
    if len(rows) > MAX_ROWS:
        raise PhotoError("Page %d has more than %d lines. Photograph it as two pages." % (page, MAX_ROWS))
    out = []
    for n, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            raise PhotoError(unclear)
        cells = [_clean_cell(c) for c in row]
        if len(cells) > len(headers):
            raise PhotoError("Page %d, line %d has more cells than the page has columns. Retake the photo square-on and try again." % (page, n))
        cells += [UNREADABLE] * (len(headers) - len(cells))
        out.append(cells)
    notes = _clean_cell(parsed.get("notes"))[:300] if parsed.get("notes") else ""
    flat = [c for r in out for c in r]
    return {"page": page, "headers": headers, "rows": out, "notes": notes,
            "unreadable": sum(1 for c in flat if c == UNREADABLE),
            "to_check": sum(1 for c in flat if c.startswith(CHECK_OPEN))}


def _used_today(school_id):
    since = timezone.now() - timedelta(hours=24)
    rows = MarkAuditLog.objects.filter(school_id=school_id, action=AUDIT_ACTION, timestamp__gte=since).values_list("details", flat=True)
    total = 0
    for d in rows:
        try:
            total += int((d or {}).get("pages", 0))
        except (TypeError, ValueError, AttributeError):
            pass
    return total


def _finish(entry, status, **extra):
    try:
        entry.details = {**(entry.details or {}), "status": status, **extra}
        entry.save(update_fields=["details"])
    except DatabaseError:
        pass


def _http_message(code, page):
    if code in (401, 403):
        return "Page %d could not be read because the reading service refused the key. Ask the system administrator to check it." % page
    if code == 429 or code >= 500:
        return "Page %d could not be read because the reading service is busy or down. Wait a minute and try that page again." % page
    return "Page %d could not be read because the reading service refused the request (%d). Try again, and tell the system administrator if it keeps happening." % (page, code)


@extend_schema(request=OpenApiTypes.OBJECT, responses={
    200: OpenApiResponse(description="One register page read. Nothing is saved."),
    400: OpenApiResponse(description="The photo could not be read."),
    403: OpenApiResponse(description="Administrator authorization required."),
    429: OpenApiResponse(description="Daily photo page limit reached."),
    502: OpenApiResponse(description="The reading service failed."),
    503: OpenApiResponse(description="Photo reading is not switched on.")})
@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser])
def migration_read_photo(request):
    school_id, error = _scope(request)
    if error:
        return error
    if not _admin(request.user):
        return Response({"detail": "Only school administrators can read photos."}, status=403)
    if request.method == "GET":
        return Response({"enabled": bool(_api_key()), "daily_pages": _daily_cap()})
    if not _api_key():
        return Response({"enabled": False, "detail": "Photo reading is not switched on yet. Use an Excel, CSV or typed PDF file for now."}, status=503)
    if school_id is None:
        raw = request.data.get("school_id")
        if not str(raw or "").isdigit() or not School.objects.filter(pk=int(raw)).exists():
            return Response({"detail": "Choose a school."}, status=400)
        school_id = int(raw)
    upload = request.FILES.get("photo")
    if upload is None:
        return Response({"detail": "Attach a photo of the register page."}, status=400)
    if upload.size > MAX_IMAGE_BYTES:
        return Response({"detail": "The photo must be 5 MB or smaller."}, status=400)
    data = upload.read()
    media = _media_type(data)
    if not media:
        return Response({"detail": "Only JPG, PNG or WebP photos can be read. Save the photo again as a JPG."}, status=400)
    page = request.data.get("page")
    page = int(page) if str(page or "").isdigit() and 1 <= int(page) <= 50 else 1
    try:
        known = _headers(request.data.get("headers"))
    except PhotoError as exc:
        return Response({"detail": str(exc)}, status=exc.status)
    cap = _daily_cap()
    if _used_today(school_id) >= cap:
        return Response({"detail": "This school has used its %d photo pages for the last 24 hours. Use an Excel, CSV or typed PDF file, or try again later." % cap}, status=429)
    entry = MarkAuditLog.objects.create(school_id=school_id, user=request.user, action=AUDIT_ACTION,
                                        details={"pages": 1, "page": page, "status": "started"})
    try:
        result = parse_page(_call_api(_body(data, media, page, known)), page, known)
    except PhotoError as exc:
        _finish(entry, "refused")
        return Response({"detail": str(exc)}, status=exc.status)
    except urllib.error.HTTPError as exc:
        _finish(entry, "failed", code=exc.code)
        return Response({"detail": _http_message(exc.code, page)}, status=502)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        _finish(entry, "failed")
        return Response({"detail": "Page %d could not be read because the reading service did not answer. Nothing was added. Try that page again." % page}, status=502)
    _finish(entry, "read", rows=len(result["rows"]), unreadable=result["unreadable"], to_check=result["to_check"])
    return Response(result)
