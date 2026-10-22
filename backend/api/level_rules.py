"""Level-based results (no marks, percentages or letter grades).

Level wording is set by the school. Nothing here is official KNEC wording.
Status moves and permissions reuse api.workflow.
"""
from django.db import transaction

from api.workflow import TRANSITIONS, _is_admin_of
from schools.models import (
    Enrollment, LevelResult, LevelScale, MarkAuditLog, TeacherAssignment,
)

ASSESSMENT_TYPES = ("opener", "mid", "end")

DEFAULT_LEVELS = [
    {"key": "exceeds", "label": "Exceeds expectation",
     "description": "Goes beyond what is expected at this stage."},
    {"key": "meets", "label": "Meets expectation",
     "description": "Shows what is expected at this stage."},
    {"key": "approaches", "label": "Approaches expectation",
     "description": "Is close to what is expected and is progressing."},
    {"key": "below", "label": "Below expectation",
     "description": "Needs extra support to reach what is expected."},
]


class LevelError(ValueError):
    pass


def clean_levels(levels):
    if not isinstance(levels, list) or not 2 <= len(levels) <= 10:
        raise LevelError("A scale needs between 2 and 10 levels.")
    out, seen = [], set()
    for x in levels:
        if not isinstance(x, dict):
            raise LevelError("Each level must have a key and a label.")
        key = str(x.get("key", "")).strip().lower()
        label = str(x.get("label", "")).strip()
        if not key or not label:
            raise LevelError("Each level needs a key and a label.")
        if key in seen:
            raise LevelError("Level keys must be different: " + key)
        seen.add(key)
        out.append({"key": key, "label": label,
                    "description": str(x.get("description", "")).strip()})
    return out


def create_scale(school, curriculum, min_level, max_level, user, levels=None):
    if not _is_admin_of(user, school.id):
        raise LevelError("Only a school administrator can change level scales.")
    if min_level > max_level:
        raise LevelError("The first level must not be above the last level.")
    cleaned = clean_levels(levels if levels is not None else DEFAULT_LEVELS)
    last = (LevelScale.objects.filter(school=school, curriculum=curriculum)
            .order_by("-version").first())
    return LevelScale.objects.create(
        school=school, curriculum=curriculum, min_level=min_level, max_level=max_level,
        version=(last.version + 1) if last else 1, source="school",
        levels=cleaned, created_by=user)


def scale_for(school_id, class_level):
    """Newest scale that covers this class level, or None (not configured)."""
    rows = LevelScale.objects.filter(
        school_id=school_id, curriculum_id=class_level.curriculum_id).order_by("-version")
    for sc in rows:
        if sc.covers(class_level):
            return sc
    return None


def _enrollment(student, year):
    return (Enrollment.objects.filter(student=student, academic_year=year)
            .select_related("class_level", "stream").first())


def _teacher_ok(user, subject, stream_id):
    return stream_id is not None and TeacherAssignment.objects.filter(
        teacher__user=user, subject=subject, stream_id=stream_id).exists()


def _audit(user, school_id, action, result, extra=None):
    d = {"level_result": result.id}
    d.update(extra or {})
    MarkAuditLog.objects.create(school_id=school_id, user=user, action=action, details=d)


@transaction.atomic
def save_level(user, student, subject, year, term, atype, level_key, comment=""):
    if atype not in ASSESSMENT_TYPES:
        raise LevelError("Unknown assessment type.")
    if term.academic_year_id != year.id:
        raise LevelError("That term is not in that academic year.")
    if student.school_id != subject.school_id:
        raise LevelError("Learner and subject belong to different schools.")
    enr = _enrollment(student, year)
    if enr is None:
        raise LevelError("This learner is not enrolled for that year.")
    if not (_is_admin_of(user, student.school_id) or _teacher_ok(user, subject, enr.stream_id)):
        raise LevelError("You are not assigned to this subject and class.")
    scale = scale_for(student.school_id, enr.class_level)
    if scale is None:
        raise LevelError("No level scale is set for this class yet.")
    if level_key not in scale.keys():
        raise LevelError("That level is not in this school's scale.")
    comment = (comment or "").strip()
    if len(comment) > 300:
        raise LevelError("The comment must be 300 characters or less.")
    row = LevelResult.objects.filter(
        student=student, subject=subject, academic_year=year, term=term,
        assessment_type=atype).first()
    if row and row.status != "draft":
        raise LevelError("Only draft results can be edited.")
    if row:
        row.scale, row.level_key, row.comment, row.entered_by = scale, level_key, comment, user
        row.save()
    else:
        row = LevelResult.objects.create(
            student=student, subject=subject, academic_year=year, term=term,
            assessment_type=atype, scale=scale, level_key=level_key,
            comment=comment, entered_by=user)
    _audit(user, student.school_id, "level_save", row, {"level": level_key})
    return row


@transaction.atomic
def move(user, result, action):
    if action not in TRANSITIONS:
        raise LevelError("Unknown action.")
    required, new_status, who = TRANSITIONS[action]
    if result.status != required:
        raise LevelError("This result is '" + result.status + "'; '" + action
                         + "' needs '" + required + "'.")
    school_id = result.student.school_id
    admin = _is_admin_of(user, school_id)
    if who == "admin" and not admin:
        raise LevelError("Only a school administrator can do this.")
    if who == "teacher_or_admin" and not admin:
        enr = _enrollment(result.student, result.academic_year)
        if enr is None or not _teacher_ok(user, result.subject, enr.stream_id):
            raise LevelError("You are not assigned to this subject and class.")
    old = result.status
    result.status = new_status
    result.save()
    _audit(user, school_id, "level_" + action, result, {"from": old, "to": new_status})
    return result


def roster(user, subject, stream, year, term, atype):
    """Learners of one stream with their current level, for the teacher's entry table."""
    if stream.school_id != subject.school_id:
        raise LevelError("Stream and subject belong to different schools.")
    if not (_is_admin_of(user, subject.school_id) or _teacher_ok(user, subject, stream.id)):
        raise LevelError("You are not assigned to this subject and class.")
    enrolled = list(Enrollment.objects.filter(
        stream=stream, academic_year=year, is_active=True).select_related("student"))
    got = {r.student_id: r for r in LevelResult.objects.filter(
        subject=subject, academic_year=year, term=term, assessment_type=atype,
        student_id__in=[e.student_id for e in enrolled])}
    scale = scale_for(subject.school_id, stream.class_level)
    rows = []
    for e in enrolled:
        r = got.get(e.student_id)
        rows.append({"student_id": e.student_id, "name": str(e.student),
                     "level": r.level_key if r else None,
                     "comment": r.comment if r else "",
                     "status": r.status if r else None})
    return {"levels": scale.levels if scale else [], "rows": rows}
