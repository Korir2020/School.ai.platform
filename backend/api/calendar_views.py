from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.calendar_rules import (
    CalendarError,
    clean_event,
    event_dict,
    events_in_range,
    read_range,
    term_dict,
    terms_in_range,
)
from api.permissions import get_user_school_id
from schools.models import CalendarEvent, SchoolAdminProfile


def _err(code, message, status):
    return Response({"error": code, "message": message}, status=status)


def _is_admin(user):
    return SchoolAdminProfile.objects.filter(user=user).exists()


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def calendar_events(request):
    sid = get_user_school_id(request.user)
    if sid is None:
        return _err("no_school", "This account is not linked to a school.", 403)
    if request.method == "GET":
        try:
            start, end = read_range(request.query_params)
        except CalendarError as exc:
            return _err("calendar_error", str(exc), 400)
        return Response(
            {
                "events": [event_dict(x) for x in events_in_range(sid, start, end)],
                "terms": [term_dict(x) for x in terms_in_range(sid, start, end)],
                "can_edit": _is_admin(request.user),
            }
        )
    if not _is_admin(request.user):
        return _err("forbidden", "Only a school administrator can change the calendar.", 403)
    try:
        data = clean_event(request.data)
    except CalendarError as exc:
        return _err("calendar_error", str(exc), 400)
    row = CalendarEvent.objects.create(school_id=sid, created_by=request.user, **data)
    return Response(event_dict(row), status=201)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def calendar_event_detail(request, pk):
    sid = get_user_school_id(request.user)
    if sid is None:
        return _err("no_school", "This account is not linked to a school.", 403)
    if not _is_admin(request.user):
        return _err("forbidden", "Only a school administrator can change the calendar.", 403)
    row = CalendarEvent.objects.filter(pk=pk, school_id=sid).first()
    if row is None:
        return _err("not_found", "Event not found.", 404)
    if request.method == "DELETE":
        row.delete()
        return Response(status=204)
    try:
        data = clean_event(request.data, current=row)
    except CalendarError as exc:
        return _err("calendar_error", str(exc), 400)
    for k, v in data.items():
        setattr(row, k, v)
    row.save()
    return Response(event_dict(row))
