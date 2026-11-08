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
    AcademicYear, ClassLevel, CurriculumPathway, Enrollment, MarkAuditLog,
    SchoolAdminProfile, Stream, Student, StudentMovement)
from .senior_rules import is_cbc_senior, pathway_matches_class

EXIT_KINDS = {"transferred", "left"}
def _bill_if_fee_authorized(student, user):
    from rest_framework.exceptions import PermissionDenied
    from api.fee_permissions import get_fee_access_school_id
    from api.fee_billing import bill_student
    try:
        get_fee_access_school_id(user, school_id=student.school_id)
    except PermissionDenied:
        return 0
    return bill_student(student)


def _admin_school(request):
    prof = SchoolAdminProfile.objects.filter(user=request.user).first()
    if not request.user.is_authenticated or not prof:
        return None, Response({"detail": "Only school admins can do this."}, status=403)
    return prof.school_id, None


def _label(enr):
    if not enr:
        return ""
    label = f"{enr.class_level.name}{' ' + enr.stream.name if enr.stream else ''}"
    return label + (f" · {enr.pathway.name}" if enr.pathway else "")


def next_level(level):
    return (ClassLevel.objects
            .filter(curriculum_id=level.curriculum_id, is_active=True, level_number__gt=level.level_number)
            .order_by("level_number").first())


def _next_level_lookup(enrollments):
    """Resolve each candidate's next class with one catalogue query."""
    curriculum_ids = {row.class_level.curriculum_id for row in enrollments}
    by_curriculum = {}
    for level in ClassLevel.objects.filter(
        curriculum_id__in=curriculum_ids, is_active=True,
    ).order_by("curriculum_id", "level_number"):
        by_curriculum.setdefault(level.curriculum_id, []).append(level)
    out = {}
    for row in enrollments:
        out[row.class_level_id] = next(
            (level for level in by_curriculum.get(row.class_level.curriculum_id, ())
             if level.level_number > row.class_level.level_number), None)
    return out


def _stream_for(school_id, level, old_stream):
    if not old_stream:
        return None
    candidates = Stream.objects.filter(
        school_id=school_id, class_level=level, is_active=True,
    ).order_by("id")
    exact = candidates.filter(name__iexact=old_stream.name).first()
    if exact:
        return exact
    # Migration 0070 appends the target grade to legacy duplicate names.
    # Keep promotion useful when a school has one such disambiguated stream.
    base = old_stream.name.split(" (", 1)[0].strip().casefold()
    if not base:
        return None
    return next(
        (stream for stream in candidates
         if stream.name.casefold().startswith(base + " (")),
        None,
    )


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
            .select_related("student", "class_level__curriculum", "stream", "pathway")
            .prefetch_related("pathway__class_levels")
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
    candidates = list(_candidates(sid, fy))
    next_levels = _next_level_lookup(candidates)
    target_ids = {next_levels[e.class_level_id].id for e in candidates
                  if next_levels.get(e.class_level_id) and is_cbc_senior(next_levels[e.class_level_id])}
    target_ids.update(e.class_level_id for e in candidates if is_cbc_senior(e.class_level))
    pathway_rows = CurriculumPathway.objects.filter(
        is_active=True, class_levels__in=target_ids,
    ).prefetch_related("class_levels").order_by("name", "id")
    paths_by_level = {}
    for pathway in pathway_rows:
        for class_level in pathway.class_levels.all():
            paths_by_level.setdefault(class_level.id, []).append(pathway)
    out = []
    for e in candidates:
        nxt = next_levels.get(e.class_level_id)
        pathways = paths_by_level.get(nxt.id, []) if nxt and is_cbc_senior(nxt) else []
        current_pathways = paths_by_level.get(e.class_level_id, []) if is_cbc_senior(e.class_level) else []
        out.append({
            "student_id": e.student_id, "name": str(e.student), "admission_number": e.student.admission_number,
            "current": _label(e), "next": nxt.name if nxt else None,
            "current_pathway_id": e.pathway_id,
            "pathway_required": bool(nxt and is_cbc_senior(nxt)),
            "current_pathway_required": is_cbc_senior(e.class_level),
            "pathways": [{"id": pathway.id, "name": pathway.name, "code": pathway.code}
                         for pathway in pathways],
            "current_pathways": [{"id": pathway.id, "name": pathway.name, "code": pathway.code}
                                  for pathway in current_pathways],
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
    submitted_pathways = request.data.get("pathways") or {}
    if not isinstance(submitted_pathways, dict):
        return Response({"detail": "pathways must map learner IDs to selected pathway IDs."}, status=400)
    parsed_pathways = {}
    for student_key, pathway_value in submitted_pathways.items():
        if not str(student_key).isdigit() or not str(pathway_value).isdigit():
            return Response({"detail": "Each pathway choice must contain valid learner and pathway IDs."}, status=400)
        parsed_pathways[int(student_key)] = int(pathway_value)
    today = datetime.date.today()
    counts = {"promoted": 0, "repeated": 0, "graduated": 0, "skipped": 0, "already": 0}
    to_bill = []
    with transaction.atomic():
        done = set(Enrollment.objects.filter(academic_year=ty).values_list("student_id", flat=True))
        candidates = list(_candidates(sid, fy))
        next_levels = _next_level_lookup(candidates)
        target_levels = {}
        required_path_ids = set()
        for e in candidates:
            if e.student_id in skip or e.student_id in done:
                continue
            level = e.class_level if e.student_id in repeat else next_levels.get(e.class_level_id)
            target_levels[e.student_id] = level
            if level and is_cbc_senior(level):
                submitted = parsed_pathways.get(e.student_id)
                pathway_id = submitted or (e.pathway_id if pathway_matches_class(e.pathway, level) else None)
                if pathway_id is None:
                    required_path_ids.add(e.student_id)
                else:
                    parsed_pathways[e.student_id] = pathway_id
        if required_path_ids:
            names = [e.student.admission_number for e in candidates if e.student_id in required_path_ids]
            return Response({"detail": "Choose a CBC Senior pathway for each learner moving into Grades 10–12.",
                             "admission_numbers": names[:50]}, status=409)
        target_pathways = {row.id: row for row in CurriculumPathway.objects.filter(
            pk__in=parsed_pathways.values(), is_active=True,
        ).prefetch_related("class_levels")}
        invalid = []
        for e in candidates:
            if e.student_id in skip or e.student_id in done:
                continue
            level = target_levels.get(e.student_id)
            selected = target_pathways.get(parsed_pathways.get(e.student_id))
            if level and is_cbc_senior(level) and not pathway_matches_class(selected, level):
                invalid.append(e.student.admission_number)
            elif level and not is_cbc_senior(level) and e.student_id in parsed_pathways:
                invalid.append(e.student.admission_number)
        if invalid:
            return Response({"detail": "One or more selected pathways are inactive or do not apply to the target grade.",
                             "admission_numbers": invalid[:50]}, status=400)
        for e in candidates:
            st = e.student
            if st.id in skip:
                counts["skipped"] += 1
                continue
            if st.id in done:
                counts["already"] += 1
                continue
            level = target_levels.get(st.id)
            e.is_active = False
            e.save(update_fields=["is_active"])
            if level is None:
                st.status = "graduated"
                st.save(update_fields=["status"])
                kind, to_label = "graduated", ""
            else:
                stream = e.stream if level.id == e.class_level_id else _stream_for(sid, level, e.stream)
                pathway = target_pathways.get(parsed_pathways.get(st.id)) if is_cbc_senior(level) else None
                new = Enrollment.objects.create(student=st, academic_year=ty, class_level=level,
                                                stream=stream, pathway=pathway)
                kind = "repeated" if st.id in repeat else "promoted"
                to_label = _label(new)
                to_bill.append(st)
            counts[kind] += 1
            StudentMovement.objects.create(
                school_id=sid, student=st, kind=kind, from_year=fy, to_year=ty,
                from_class=_label(e), to_class=to_label, effective_date=today, recorded_by=request.user)
        MarkAuditLog.objects.create(school_id=sid, user=request.user, action="students_promoted",
                                    details={"from_year": fy.name, "to_year": ty.name, **counts})
    for st in to_bill:
        _bill_if_fee_authorized(st, request.user)
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
    pathway = None
    raw_pathway = request.data.get("pathway")
    if is_cbc_senior(level):
        try:
            pathway = CurriculumPathway.objects.filter(pk=int(raw_pathway), is_active=True).prefetch_related(
                "class_levels").first()
        except (TypeError, ValueError):
            pathway = None
        if not pathway_matches_class(pathway, level):
            return Response({"detail": "Choose an active CBC Senior pathway for this grade."}, status=400)
    elif raw_pathway not in (None, ""):
        return Response({"detail": "Pathways apply only to CBC Senior Grades 10–12."}, status=400)
    with transaction.atomic():
        Enrollment.objects.filter(student=st, academic_year=year).update(is_active=False)
        new = Enrollment.objects.create(student=st, academic_year=year, class_level=level,
                                        stream=stream, pathway=pathway)
        st.status = "active"
        st.save(update_fields=["status"])
        m = StudentMovement.objects.create(
            school_id=st.school_id, student=st, kind="readmitted", to_year=year, to_class=_label(new),
            reason=str(request.data.get("reason", "")).strip()[:300],
            effective_date=datetime.date.today(), recorded_by=request.user)
        MarkAuditLog.objects.create(school_id=st.school_id, user=request.user, action="student_readmitted",
                                    details={"student_id": st.id})
    _bill_if_fee_authorized(st, request.user)
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
