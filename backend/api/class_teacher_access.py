"""Narrow report access for a class teacher: only the meta, readiness and
student PDF routes, only the stream(s) they are class teacher of, only
published exams, never provisional. Teachers who are not class teachers
stay denied everywhere."""
from marian_reports.domain import NotFound, PermissionDenied, User

from schools.models import (
    ClassTeacher, Enrollment, Exam, SchoolAdminProfile, TeacherProfile,
)


def _pk(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _route_ok(path):
    return (path.endswith("/meta/") or path.endswith("/selection/")
            or ("/student/" in path and path.endswith("/pdf/")))


def _rows(django_user, year_id=None):
    qs = ClassTeacher.objects.filter(teacher__user=django_user).select_related(
        "stream__class_level", "academic_year")
    if year_id is not None:
        return list(qs.filter(academic_year_id=year_id))
    rows = list(qs)
    if not rows:
        return []
    latest = max(r.academic_year.start_date for r in rows)
    return [r for r in rows if r.academic_year.start_date == latest]


def _pairs(rows):
    return {(r.stream.class_level.name, r.stream.name) for r in rows}


def class_teacher_user(request):
    u = request.user
    if not _route_ok(request.path):
        raise PermissionDenied("teachers do not open this report page")
    if SchoolAdminProfile.objects.filter(user=u).exists():
        raise PermissionDenied("no report access")
    tp = TeacherProfile.objects.filter(user=u).first()
    if tp is None:
        raise PermissionDenied("no report access")
    rows = list(ClassTeacher.objects.filter(teacher=tp).select_related("stream__class_level"))
    if not rows:
        raise PermissionDenied("only class teachers open reports")
    names = tuple(sorted({r.stream.class_level.name for r in rows}))
    return User(str(u.pk), str(tp.school_id), "teacher", class_names=names)


def _no_provisional(request):
    if request.query_params.get("provisional") == "1":
        raise PermissionDenied("provisional reports are not available to class teachers")


def _exam(user, exam_id):
    pk = _pk(exam_id)
    exam = None
    if pk is not None:
        exam = (Exam.objects.filter(pk=pk, school_id=_pk(user.school_id))
                .select_related("term").first())
    if exam is None:
        raise NotFound("exam")
    if exam.status != "published":
        raise PermissionDenied("results are not published yet")
    return exam


def limit_meta(django_user, studs, exams):
    pairs = _pairs(_rows(django_user))
    studs = [s for s in studs if (s.class_name, s.stream) in pairs]
    return studs, [e for e in exams if e["published"]]


def enforce_selection(request, user, exam_id, cn, stream, ids):
    _no_provisional(request)
    exam = _exam(user, exam_id)
    year = exam.term.academic_year_id
    allowed = sorted(n for c, n in _pairs(_rows(request.user, year)) if c == cn)
    if not stream:
        if len(allowed) != 1:
            raise PermissionDenied("choose your stream")
        stream = allowed[0]
    if stream not in allowed:
        raise PermissionDenied("not your stream")
    if ids:
        pks = {_pk(i) for i in ids}
        if None in pks:
            raise PermissionDenied("not your stream")
        have = (Enrollment.objects.filter(
            student_id__in=pks, academic_year_id=year, class_level__name=cn,
            stream__name=stream, student__school_id=_pk(user.school_id))
            .values("student_id").distinct().count())
        if have != len(pks):
            raise PermissionDenied("not your stream")
    return stream, ids


def enforce_student(request, user, st):
    _no_provisional(request)
    exam = _exam(user, request.query_params.get("exam_id", ""))
    pairs = _pairs(_rows(request.user, exam.term.academic_year_id))
    if (st.class_name, st.stream) not in pairs:
        raise PermissionDenied("not your stream")
