"""Year-end promotion, repeats, exits (transfer / left) and re-admission.

Only school admins of the learner's own school may change anything.
Old enrollments are kept (made inactive) so past marks, reports and fees
remain intact; every change is written to StudentMovement and the audit log.
"""
import datetime

from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    AcademicYear, ClassLevel, Enrollment, MarkAuditLog, SchoolAdminProfile,
    Stream, Student, StudentMovement)

EXIT_KINDS = {"transferred", "left"}


def _admin_school(request):
    prof = SchoolAdminProfile.objects.filter(user=request.user).first()
    if not request.user.is_authenticated or not prof:
        return None, Response({"detail": "Only school admins can do this."}, status=403)
    return prof.school_id, None


def _label(enr):
    if not enr:
        return ""
    return f"{enr.class_level.name}{' ' + enr.stream.name if enr.stream else ''}"


def next_level(level):
    return (ClassLevel.objects
            .filter(curriculum_id=level.curriculum_id, is_active=True, level_number__gt=level.level_number)
            .order_by("level_number").first())


def _stream_for(school_id, level, old_stream):
    if not old_stream:
        return None
    return Stream.objects.filter(school_id=school_id, class_level=level, name__iexact=old_stream.name,
                                 is_active=True).first()


def _years(request, sid):
    try:
        fy = AcademicYear.objects.get(pk=int(request.data.get("from_year") if request.method == "POST" else request.query_params.get("from_year")), school_id=sid)
        ty = AcademicYear.objects.get(pk=int(request.data.get("to_year") if request.method == "POST" else request.query_params.get("to_year")), school_id=sid)
    except (TypeError, ValueError, AcademicYear.DoesNotExist):
        return None, None, Response({"detail": "Choose the current year and the new year."}, status=400)
    if fy.id == ty.id:
        return None, None, Response({"detail": "The new year must be different from the current year."}, status=400)
    if ty.start_date <= fy.start_date:
        return None, None, Response({"detail": "The new year must start after the current year."}, status=400)
    return fy, ty, None


def _candidates(sid, fy):
    return (Enrollment.objects
            .filter(academic_year=fy, is_active=True, student__school_id=sid, student__status="active")
            .select_related("student", "class_level", "stream")
            .order_by("class_level__level_number", "stream__name", "student__admission_number"))


@api_view(["GET"])
def promotion_years(request):
    sid, err = _admin_school(request)
    if err:
        return err
    rows = AcademicYear.objects.filter(school_id=sid).order_by("start_date")
    return Response([{"id": y.id, "name": y.name, "start_date": y.start_date, "is_active": y.is_active} for y in rows])


@api_view(["GET"])
def promotion_preview(request):
    sid, err = _admin_school(request)
    if err:
        return err
    fy, ty, err = _years(request, sid)
    if err:
        return err
    done = set(Enrollment.objects.filter(academic_year=ty).values_list("student_id", flat=True))
    out = []
    for e in _candidates(sid, fy):
        nxt = next_level(e.class_level)
        out.append({
            "student_id": e.student_id, "name": str(e.student), "admission_number": e.student.admission_number,
            "current": _label(e), "next": nxt.name if nxt else None,
            "already_moved": e.student_id in done,
        })
    return Response({"from_year": fy.name, "to_year": ty.name, "students": out})


@api_view(["POST"])
def promotion_run(request):
    sid, err = _admin_school(request)
    if err:
        return err
    fy, ty, err = _years(request, sid)
    if err:
        return err
    repeat = {int(x) for x in request.data.get("repeat") or [] if str(x).isdigit()}
    skip = {int(x) for x in request.data.get("skip") or [] if str(x).isdigit()}
    today = datetime.date.today()
    counts = {"promoted": 0, "repeated": 0, "graduated": 0, "skipped": 0, "already": 0}
    to_bill = []
    with transaction.atomic():
        done = set(Enrollment.objects.filter(academic_year=ty).values_list("student_id", flat=True))
        for e in list(_candidates(sid, fy)):
            st = e.student
            if st.id in skip:
                counts["skipped"] += 1
                continue
            if st.id in done:
                counts["already"] += 1
                continue
            level = e.class_level if st.id in repeat else next_level(e.class_level)
            e.is_active = False
            e.save(update_fields=["is_active"])
            if level is None:
                st.status = "graduated"
                st.save(update_fields=["status"])
                kind, to_label = "graduated", ""
            else:
                stream = e.stream if level.id == e.class_level_id else _stream_for(sid, level, e.stream)
                new = Enrollment.objects.create(student=st, academic_year=ty, class_level=level, stream=stream)
                kind = "repeated" if st.id in repeat else "promoted"
                to_label = _label(new)
                to_bill.append(st)
            counts[kind] += 1
            StudentMovement.objects.create(
                school_id=sid, student=st, kind=kind, from_year=fy, to_year=ty,
                from_class=_label(e), to_class=to_label, effective_date=today, recorded_by=request.user)
        MarkAuditLog.objects.create(school_id=sid, user=request.user, action="students_promoted",
                                    details={"from_year": fy.name, "to_year": ty.name, **counts})
    from api.fee_billing import bill_student
    for st in to_bill:
        bill_student(st)
    return Response(counts)


def _student(request, pk):
    sid, err = _admin_school(request)
    if err:
        return None, err
    st = Student.objects.filter(pk=pk, school_id=sid).first()
    if not st:
        return None, Response({"detail": "Not found."}, status=404)
    return st, None


def _row(m):
    return {"id": m.id, "kind": m.kind, "label": m.get_kind_display(), "from_class": m.from_class,
            "to_class": m.to_class, "destination": m.destination, "reason": m.reason,
            "effective_date": m.effective_date, "from_year": m.from_year.name if m.from_year else None,
            "to_year": m.to_year.name if m.to_year else None,
            "recorded_by": m.recorded_by.username if m.recorded_by else None}


@api_view(["GET"])
def student_movements(request, pk):
    st, err = _student(request, pk)
    if err:
        return err
    return Response({"status": st.status, "movements": [_row(m) for m in st.movements.all()]})


def _parse_date(value):
    if not value:
        return datetime.date.today()
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


@api_view(["POST"])
def student_exit(request, pk):
    st, err = _student(request, pk)
    if err:
        return err
    kind = str(request.data.get("kind", ""))
    if kind not in EXIT_KINDS:
        return Response({"detail": "Choose transferred or left."}, status=400)
    if st.status != "active":
        return Response({"detail": "This student is not currently active."}, status=409)
    when = _parse_date(request.data.get("effective_date"))
    if when is None:
        return Response({"detail": "Enter a valid date."}, status=400)
    destination = str(request.data.get("destination", "")).strip()[:200]
    reason = str(request.data.get("reason", "")).strip()[:300]
    if kind == "transferred" and not destination:
        return Response({"detail": "Enter the school the student is moving to."}, status=400)
    with transaction.atomic():
        current = Enrollment.objects.filter(student=st, is_active=True).select_related("class_level", "stream", "academic_year").first()
        Enrollment.objects.filter(student=st, is_active=True).update(is_active=False)
        st.status = kind
        st.save(update_fields=["status"])
        m = StudentMovement.objects.create(
            school_id=st.school_id, student=st, kind=kind, from_year=current.academic_year if current else None,
            from_class=_label(current), destination=destination, reason=reason,
            effective_date=when, recorded_by=request.user)
        MarkAuditLog.objects.create(school_id=st.school_id, user=request.user, action=f"student_{kind}",
                                    details={"student_id": st.id, "admission_number": st.admission_number})
    return Response(_row(m))


@api_view(["POST"])
def student_readmit(request, pk):
    st, err = _student(request, pk)
    if err:
        return err
    if st.status == "active":
        return Response({"detail": "This student is already active."}, status=409)
    year = AcademicYear.objects.filter(school_id=st.school_id, is_active=True).order_by("-start_date").first()
    if not year:
        return Response({"detail": "Set an active academic year first."}, status=400)
    try:
        level = ClassLevel.objects.get(pk=int(request.data.get("class_level")))
    except (TypeError, ValueError, ClassLevel.DoesNotExist):
        return Response({"detail": "Choose the class to re-admit into."}, status=400)
    stream = None
    if str(request.data.get("stream") or "").isdigit():
        stream = Stream.objects.filter(pk=request.data.get("stream"), school_id=st.school_id, class_level=level).first()
        if not stream:
            return Response({"detail": "That stream is not in the chosen class."}, status=400)
    with transaction.atomic():
        Enrollment.objects.filter(student=st, academic_year=year).update(is_active=False)
        new = Enrollment.objects.create(student=st, academic_year=year, class_level=level, stream=stream)
        st.status = "active"
        st.save(update_fields=["status"])
        m = StudentMovement.objects.create(
            school_id=st.school_id, student=st, kind="readmitted", to_year=year, to_class=_label(new),
            reason=str(request.data.get("reason", "")).strip()[:300],
            effective_date=datetime.date.today(), recorded_by=request.user)
        MarkAuditLog.objects.create(school_id=st.school_id, user=request.user, action="student_readmitted",
                                    details={"student_id": st.id})
    from api.fee_billing import bill_student
    bill_student(st)
    return Response(_row(m))


@api_view(["GET"])
def former_students(request):
    sid, err = _admin_school(request)
    if err:
        return err
    rows = Student.objects.filter(school_id=sid).exclude(status="active").order_by("last_name", "first_name")
    last = {}
    for m in StudentMovement.objects.filter(school_id=sid, kind__in=["transferred", "left", "graduated"]).order_by("created_at"):
        last[m.student_id] = m
    return Response([{
        "id": s.id, "name": str(s), "admission_number": s.admission_number, "status": s.status,
        "last_class": last[s.id].from_class if s.id in last else "",
        "destination": last[s.id].destination if s.id in last else "",
        "date": last[s.id].effective_date if s.id in last else None,
    } for s in rows])
