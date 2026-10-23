from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.framework_rules import is_authorized
from api.permissions import get_user_school_id
from schools.models import (
    AcademicYear, ClassTeacher, NationalRecord, Stream, Student, TeacherProfile,
)

EXAMS = dict(NationalRecord.EXAM_CHOICES)


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


def _nr(r):
    return {"id": r.id, "student_id": r.student_id,
            "name": (r.student.first_name + " " + r.student.last_name).strip(),
            "exam_type": r.exam_type, "year": r.year, "subject_name": r.subject_name,
            "result": r.result, "note": r.note}


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def national_records(request):
    sid, bad = _admin(request)
    if bad:
        return bad
    if request.method == "GET":
        qs = NationalRecord.objects.filter(school_id=sid).select_related("student")
        stu = _pk(request.query_params.get("student_id"))
        if stu is not None:
            qs = qs.filter(student_id=stu)
        et = request.query_params.get("exam_type")
        if et in EXAMS:
            qs = qs.filter(exam_type=et)
        return Response({"records": [_nr(r) for r in qs.order_by("exam_type", "-year", "subject_name")[:500]]})
    d = request.data
    student = Student.objects.filter(pk=_pk(d.get("student_id")), school_id=sid).first()
    if student is None:
        return _err("not_found", "Not found: student.", 404)
    et = str(d.get("exam_type", ""))
    if et not in EXAMS:
        return _err("invalid_record", "Choose KPSEA, KJSEA or KCSE.", 400)
    year = _pk(d.get("year"))
    if year is None or not 1990 <= year <= 2100:
        return _err("invalid_record", "Enter the year of the national exam.", 400)
    result = str(d.get("result", "")).strip()
    if not result or len(result) > 40:
        return _err("invalid_record", "Type the result exactly as on the official result (up to 40 characters).", 400)
    subject = str(d.get("subject_name", "")).strip()[:80]
    note = str(d.get("note", "")).strip()[:200]
    row, _ = NationalRecord.objects.update_or_create(
        student=student, exam_type=et, year=year, subject_name=subject,
        defaults={"school_id": sid, "result": result, "note": note, "entered_by": request.user})
    row = NationalRecord.objects.select_related("student").get(pk=row.pk)
    return Response(_nr(row))
