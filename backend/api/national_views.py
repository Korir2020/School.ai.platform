from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.framework_rules import is_authorized
from api.permissions import get_user_school_id
from schools.models import (
    AcademicYear, ClassTeacher, Stream, TeacherProfile,
)



def _err(code, message, status):
    return Response({"error": code, "message": message}, status=status)


def _pk(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _admin(request):
    if not is_authorized(request.user):
        return None, _err("forbidden", "Only a school administrator can manage this.", 403)
    sid = get_user_school_id(request.user)
    if sid is None:
        return None, _err("forbidden", "School access not assigned.", 403)
    return sid, None


def _ct(r):
    t = r.teacher.user
    return {"id": r.id, "stream_id": r.stream_id,
            "stream_name": r.stream.class_level.name + " " + r.stream.name,
            "year_id": r.academic_year_id, "year_name": r.academic_year.name,
            "teacher_id": r.teacher_id, "teacher_name": t.get_full_name() or t.username}


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def class_teachers(request):
    sid, bad = _admin(request)
    if bad:
        return bad
    if request.method == "GET":
        qs = ClassTeacher.objects.filter(school_id=sid).select_related(
            "stream__class_level", "teacher__user", "academic_year")
        yr = _pk(request.query_params.get("year_id"))
        if yr is not None:
            qs = qs.filter(academic_year_id=yr)
        qs = qs.order_by("academic_year_id", "stream__class_level__level_number", "stream__name")
        streams = Stream.objects.filter(school_id=sid, is_active=True).select_related(
            "class_level").order_by("class_level__level_number", "name")
        teachers = TeacherProfile.objects.filter(
            school_id=sid, user__is_active=True).select_related("user").order_by("id")
        years = AcademicYear.objects.filter(school_id=sid).order_by("-start_date")
        return Response({
            "class_teachers": [_ct(r) for r in qs],
            "options": {
                "streams": [{"id": x.id, "name": x.class_level.name + " " + x.name} for x in streams],
                "teachers": [{"id": t.id, "name": t.user.get_full_name() or t.user.username} for t in teachers],
                "years": [{"id": y.id, "name": y.name} for y in years],
            },
        })
    d = request.data
    stream = Stream.objects.filter(pk=_pk(d.get("stream_id")), school_id=sid).first()
    year = AcademicYear.objects.filter(pk=_pk(d.get("year_id")), school_id=sid).first()
    teacher = TeacherProfile.objects.filter(pk=_pk(d.get("teacher_id")), school_id=sid).first()
    for obj, name in ((stream, "stream"), (year, "academic year"), (teacher, "teacher")):
        if obj is None:
            return _err("not_found", "Not found: " + name + ".", 404)
    row, _ = ClassTeacher.objects.update_or_create(
        stream=stream, academic_year=year,
        defaults={"school_id": sid, "teacher": teacher, "assigned_by": request.user})
    row = ClassTeacher.objects.select_related(
        "stream__class_level", "teacher__user", "academic_year").get(pk=row.pk)
    return Response(_ct(row))
