"""Framework lookup, versioning and change rules.

Rules are set by the school. Nothing here is an official KNEC rule.
"""
from django.db import transaction

from schools.models import (
    Exam, FrameworkChangeLog, FrameworkSetting, FrameworkVersion, SchoolAdminProfile,
)

LEGACY = "legacy_untracked"


class FrameworkError(ValueError):
    pass


def is_authorized(user):
    """Same rule exam publishing uses: superuser or a school admin."""
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or SchoolAdminProfile.objects.filter(user=user).exists())


def resolve(school_id, class_level, academic_year=None):
    """Most specific setting wins: level+year, level, year, school default.
    Returns a FrameworkVersion or None (None means not configured)."""
    rows = FrameworkSetting.objects.filter(school_id=school_id).select_related("framework_version")
    order = []
    if academic_year is not None:
        order.append(dict(class_level=class_level, academic_year=academic_year))
    order.append(dict(class_level=class_level, academic_year=None))
    if academic_year is not None:
        order.append(dict(class_level=None, academic_year=academic_year))
    order.append(dict(class_level=None, academic_year=None))
    for q in order:
        hit = rows.filter(**q).first()
        if hit and hit.framework_version.covers(class_level):
            return hit.framework_version
    return None


def next_version(school_id, framework_key):
    last = (FrameworkVersion.objects.filter(school_id=school_id, framework_key=framework_key)
            .order_by("-version").first())
    return (last.version + 1) if last else 1


def create_version(school, framework_key, curriculum, min_level, max_level, user, rules=None):
    from marian_reports.frameworks import FRAMEWORKS
    if framework_key not in FRAMEWORKS:
        raise FrameworkError("Unknown framework: " + str(framework_key))
    if min_level > max_level:
        raise FrameworkError("The first level must not be above the last level.")
    return FrameworkVersion.objects.create(
        school=school, framework_key=framework_key, version=next_version(school.id, framework_key),
        curriculum=curriculum, min_level=min_level, max_level=max_level,
        source="school", rules=rules or {}, created_by=user,
    )


def results_exist(school_id, class_level=None, academic_year=None):
    qs = Exam.objects.filter(school_id=school_id, status="published")
    if class_level is not None:
        qs = qs.filter(class_level=class_level)
    if academic_year is not None:
        qs = qs.filter(term__academic_year=academic_year)
    return qs.exists()


@transaction.atomic
def assign(school, version, user, class_level=None, academic_year=None, approver=None):
    """Set the school default (class_level None) or an override.
    Refuses incompatible levels. If published results exist for the scope,
    a second authorized user must approve."""
    if not is_authorized(user):
        raise FrameworkError("Only a school administrator can change frameworks.")
    if version.school_id != school.id:
        raise FrameworkError("That framework version belongs to another school.")
    if class_level is not None and not version.covers(class_level):
        raise FrameworkError("This framework does not cover " + class_level.name + ".")
    existed = results_exist(school.id, class_level, academic_year)
    if existed:
        if approver is None or not is_authorized(approver) or approver.pk == user.pk:
            raise FrameworkError(
                "Published results exist. A different authorized user must approve this change.")
    row = FrameworkSetting.objects.filter(
        school=school, class_level=class_level, academic_year=academic_year).first()
    old = row.framework_version if row else None
    if row:
        row.framework_version = version
        row.updated_by = user
        row.save()
    else:
        row = FrameworkSetting.objects.create(
            school=school, class_level=class_level, academic_year=academic_year,
            framework_version=version, updated_by=user)
    FrameworkChangeLog.objects.create(
        school=school, class_level=class_level, academic_year=academic_year,
        from_version=old, to_version=version, changed_by=user,
        approved_by=approver if existed else None, results_existed=existed)
    return row


def record_on_exam(exam):
    """Called at publish. Stores the framework and version used. Never blocks publishing."""
    v = resolve(exam.school_id, exam.class_level, exam.term.academic_year)
    if v is not None:
        exam.framework_key = v.framework_key
        exam.framework_version = v.version
    return v
