from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.level_rules import LevelError, create_scale, move, roster, save_level
from api.permissions import get_user_school_id
from schools.models import (
    AcademicYear, Curriculum, LevelResult, LevelScale, School, Stream, Student, Subject, Term,
)


def _err(code, message, status):
    return Response({"error": code, "message": message}, status=status)


def _find(model, request, pk, school_field):
    try:
        pk = int(pk)
    except (TypeError, ValueError):
        return None
    qs = model.objects.filter(pk=pk)
    if not request.user.is_superuser:
        sid = get_user_school_id(request.user)
        if sid is None:
            return None
        qs = qs.filter(**{school_field: sid})
    return qs.first()


def _need(request, spec):
    out = {}
    data = request.query_params if request.method == "GET" else request.data
    for name, (model, field) in spec.items():
        obj = _find(model, request, data.get(name + "_id"), field)
        if obj is None:
            return _err("not_found", "Not found: " + name + ".", 404)
        out[name] = obj
    return out


_CTX = {
    "subject": (Subject, "school_id"),
    "year": (AcademicYear, "school_id"),
    "term": (Term, "academic_year__school_id"),
}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def level_roster(request):
    got = _need(request, dict(_CTX, stream=(Stream, "school_id")))
    if isinstance(got, Response):
        return got
    try:
        return Response(roster(request.user, got["subject"], got["stream"], got["year"],
                               got["term"], request.query_params.get("type", "end")))
    except LevelError as e:
        return _err("level_error", str(e), 400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def level_save(request):
    got = _need(request, dict(_CTX, student=(Student, "school_id")))
    if isinstance(got, Response):
        return got
    try:
        row = save_level(request.user, got["student"], got["subject"], got["year"],
                         got["term"], request.data.get("type", "end"),
                         str(request.data.get("level", "")), request.data.get("comment", ""))
    except LevelError as e:
        return _err("level_error", str(e), 400)
    return Response({"id": row.id, "level": row.level_key,
                     "comment": row.comment, "status": row.status})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def level_move(request):
    row = _find(LevelResult, request, request.data.get("result_id"), "student__school_id")
    if row is None:
        return _err("not_found", "Not found.", 404)
    try:
        move(request.user, row, str(request.data.get("action", "")))
    except LevelError as e:
        return _err("level_error", str(e), 400)
    return Response({"id": row.id, "status": row.status})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def level_scales(request):
    sid = get_user_school_id(request.user)
    if sid is None:
        return _err("forbidden", "School access not assigned.", 403)
    school = School.objects.get(pk=sid)
    if request.method == "GET":
        rows = LevelScale.objects.filter(school=school).order_by("curriculum_id", "-version")
        return Response({"scales": [
            {"id": s.id, "curriculum_id": s.curriculum_id, "min_level": s.min_level,
             "max_level": s.max_level, "version": s.version, "source": s.source,
             "levels": s.levels} for s in rows]})
    cid = str(request.data.get("curriculum_id", ""))
    cur = Curriculum.objects.filter(pk=int(cid)).first() if cid.isdigit() else None
    if cur is None:
        return _err("not_found", "Not found: curriculum.", 404)
    try:
        sc = create_scale(school, cur, int(request.data.get("min_level")),
                          int(request.data.get("max_level")), request.user,
                          request.data.get("levels"))
    except (TypeError, ValueError) as e:
        return _err("level_error", str(e) or "Check the level numbers.", 400)
    return Response({"id": sc.id, "version": sc.version, "levels": sc.levels})
