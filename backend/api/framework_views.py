from django.contrib.auth import authenticate
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.framework_rules import (
    FrameworkError, assign, create_version, is_authorized, resolve, results_exist,
)
from api.permissions import get_user_school_id
from marian_reports.frameworks import FRAMEWORKS
from schools.models import (
    AcademicYear, ClassLevel, Curriculum, FrameworkSetting, FrameworkVersion, School,
)


def _err(code, message, status):
    return Response({"error": code, "message": message}, status=status)


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _ctx(request):
    if not is_authorized(request.user):
        return None, _err("forbidden", "Only a school administrator can manage frameworks.", 403)
    sid = get_user_school_id(request.user)
    if sid is None:
        return None, _err("forbidden", "School access not assigned.", 403)
    return School.objects.get(pk=sid), None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def framework_overview(request):
    school, bad = _ctx(request)
    if bad:
        return bad
    levels = list(ClassLevel.objects.filter(is_active=True)
                  .select_related("curriculum").order_by("curriculum_id", "level_number"))
    effective = []
    for c in levels:
        v = resolve(school.id, c, None)
        effective.append({"class_level_id": c.id,
                          "framework_key": v.framework_key if v else None,
                          "version": v.version if v else None})
    versions = FrameworkVersion.objects.filter(school=school).select_related("curriculum") \
        .order_by("framework_key", "-version")
    settings = FrameworkSetting.objects.filter(school=school).select_related("framework_version")
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    return Response({
        "frameworks": [{"key": f.key, "name": f.name, "stage": f.stage} for f in FRAMEWORKS.values()],
        "class_levels": [{"id": c.id, "name": c.name, "level_number": c.level_number,
                          "curriculum_id": c.curriculum_id, "curriculum_name": c.curriculum.name}
                         for c in levels],
        "versions": [{"id": v.id, "framework_key": v.framework_key, "version": v.version,
                      "curriculum_id": v.curriculum_id, "curriculum_name": v.curriculum.name,
                      "min_level": v.min_level, "max_level": v.max_level, "source": v.source,
                      "frozen_scale": bool(isinstance(v.rules, dict) and v.rules.get("scheme"))}
                     for v in versions],
        "settings": [{"id": s.id, "class_level_id": s.class_level_id,
                      "academic_year_id": s.academic_year_id,
                      "framework_key": s.framework_version.framework_key,
                      "version": s.framework_version.version} for s in settings],
        "years": [{"id": y.id, "name": y.name} for y in years],
        "effective": effective,
        "published_results_exist": results_exist(school.id),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def framework_version(request):
    school, bad = _ctx(request)
    if bad:
        return bad
    d = request.data
    cur = Curriculum.objects.filter(pk=_int(d.get("curriculum_id"))).first()
    if cur is None:
        return _err("not_found", "Not found: curriculum.", 404)
    lo, hi = _int(d.get("min_level")), _int(d.get("max_level"))
    if lo is None or hi is None:
        return _err("framework_error", "Check the level numbers.", 400)
    try:
        rules = None
        if d.get("freeze_school_scale") in (True, "true", "1", 1):
            from api.report_source import DjangoConfigStore, scheme_to_dict
            current = DjangoConfigStore(str(school.id)).load_scheme()
            if current is None:
                return _err("no_grading_scale", "Set the school's grading scale first.", 400)
            rules = {"scheme": scheme_to_dict(current)}
        v = create_version(school, str(d.get("framework_key", "")), cur, lo, hi, request.user, rules=rules)
    except FrameworkError as e:
        return _err("framework_error", str(e), 400)
    return Response({"id": v.id, "framework_key": v.framework_key, "version": v.version,
                     "frozen_scale": bool(rules)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def framework_assign(request):
    school, bad = _ctx(request)
    if bad:
        return bad
    d = request.data
    version = FrameworkVersion.objects.filter(pk=_int(d.get("version_id")), school=school).first()
    if version is None:
        return _err("not_found", "Not found: framework version.", 404)
    cl = None
    if d.get("class_level_id") not in (None, ""):
        cl = ClassLevel.objects.filter(pk=_int(d.get("class_level_id"))).first()
        if cl is None:
            return _err("not_found", "Not found: class level.", 404)
    yr = None
    if d.get("year_id") not in (None, ""):
        yr = AcademicYear.objects.filter(pk=_int(d.get("year_id")), school=school).first()
        if yr is None:
            return _err("not_found", "Not found: academic year.", 404)
    approver = None
    if d.get("approver_username"):
        approver = authenticate(username=str(d.get("approver_username")),
                                password=str(d.get("approver_password", "")))
        if approver is None:
            return _err("approver_failed", "The second administrator could not be signed in.", 400)
    needed = results_exist(school.id, cl, yr)
    try:
        row = assign(school, version, request.user, class_level=cl, academic_year=yr,
                     approver=approver)
    except FrameworkError as e:
        return _err("framework_error", str(e), 400)
    return Response({"id": row.id, "framework_key": version.framework_key,
                     "version": version.version, "second_approval_used": bool(needed)})
