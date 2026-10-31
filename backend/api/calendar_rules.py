from django.db.models import Q
from django.utils.dateparse import parse_date

from schools.models import CalendarEvent, Term

KINDS = [k for k, _ in CalendarEvent.KINDS]
MAX_SPAN_DAYS = 366
MAX_RANGE_DAYS = 400


class CalendarError(Exception):
    pass


def _date(value, label):
    d = None
    if isinstance(value, str):
        try:
            d = parse_date(value.strip())
        except ValueError:
            d = None
    if d is None:
        raise CalendarError(label + " must be a date like 2026-03-15.")
    return d


def clean_event(data, current=None):
    merged = {}
    if current is not None:
        merged = {
            "title": current.title,
            "kind": current.kind,
            "start_date": current.start_date.isoformat(),
            "end_date": current.end_date.isoformat() if current.end_date else None,
            "location": current.location,
            "notes": current.notes,
        }
    for key in ("title", "kind", "start_date", "end_date", "location", "notes"):
        if key in data:
            merged[key] = data[key]
    title = str(merged.get("title") or "").strip()
    if not title:
        raise CalendarError("Give the event a title.")
    if len(title) > 120:
        raise CalendarError("The title is too long (120 characters at most).")
    kind = str(merged.get("kind") or "event").strip()
    if kind not in KINDS:
        raise CalendarError("Kind must be one of: " + ", ".join(KINDS) + ".")
    start = _date(merged.get("start_date"), "Start date")
    end = None
    if merged.get("end_date") not in (None, ""):
        end = _date(merged.get("end_date"), "End date")
        if end < start:
            raise CalendarError("The end date cannot be before the start date.")
        if (end - start).days > MAX_SPAN_DAYS:
            raise CalendarError("An event cannot last longer than 366 days.")
    location = str(merged.get("location") or "").strip()
    notes = str(merged.get("notes") or "").strip()
    if len(location) > 120:
        raise CalendarError("The location is too long (120 characters at most).")
    if len(notes) > 1000:
        raise CalendarError("The notes are too long (1000 characters at most).")
    return {
        "title": title,
        "kind": kind,
        "start_date": start,
        "end_date": end,
        "location": location,
        "notes": notes,
    }


def read_range(params):
    start = _date(params.get("from"), "from")
    end = _date(params.get("to"), "to")
    if end < start:
        raise CalendarError("to cannot be before from.")
    if (end - start).days > MAX_RANGE_DAYS:
        raise CalendarError("Ask for at most 400 days at a time.")
    return start, end


def events_in_range(school_id, start, end):
    return CalendarEvent.objects.filter(school_id=school_id, start_date__lte=end).filter(
        Q(end_date__gte=start) | Q(end_date__isnull=True, start_date__gte=start)
    )


def terms_in_range(school_id, start, end):
    return (
        Term.objects.filter(
            academic_year__school_id=school_id, start_date__lte=end, end_date__gte=start
        )
        .select_related("academic_year")
        .order_by("start_date")
    )


def event_dict(e):
    return {
        "id": e.id,
        "title": e.title,
        "kind": e.kind,
        "start_date": e.start_date.isoformat(),
        "end_date": e.end_date.isoformat() if e.end_date else None,
        "location": e.location,
        "notes": e.notes,
    }


def term_dict(t):
    return {
        "id": t.id,
        "name": t.name,
        "year": t.academic_year.name,
        "start_date": t.start_date.isoformat(),
        "end_date": t.end_date.isoformat(),
    }
