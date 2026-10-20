"""Map a logged-in Marian user to a marian_reports User.

Identity comes ONLY from the login, never from request parameters.
Roles follow api/permissions.py: SchoolAdminProfile -> admin,
TeacherProfile -> teacher, GuardianProfile -> guardian.
Superusers have no school, so report access is denied for them.
Known limit: teachers are limited by CLASS name, but Marian's
TeacherAssignment is per subject and stream (stricter).
"""
from marian_reports.domain import PermissionDenied, User

from schools.models import (
    GuardianProfile, SchoolAdminProfile, StudentGuardian,
    TeacherAssignment, TeacherProfile,
)


def build_report_user(user):
    if user is None or not getattr(user, "is_authenticated", False) \
            or user.is_superuser:
        raise PermissionDenied("no report access")
    uid = str(user.pk)
    admin = SchoolAdminProfile.objects.filter(user=user).first()
    if admin:
        return User(uid, str(admin.school_id), "admin", can_view_fees=True)
    teacher = TeacherProfile.objects.filter(user=user).first()
    if teacher:
        levels = TeacherAssignment.objects.filter(
            teacher=teacher, school_id=teacher.school_id,
        ).values_list("stream__class_level__name", flat=True)
        return User(uid, str(teacher.school_id), "teacher",
                    class_names=tuple(sorted(set(levels))))
    guardian = GuardianProfile.objects.filter(user=user).first()
    if guardian:
        ids = StudentGuardian.objects.filter(
            guardian=guardian, student__school_id=guardian.school_id,
        ).values_list("student_id", flat=True)
        return User(uid, str(guardian.school_id), "guardian",
                    student_ids=tuple(sorted(str(i) for i in ids)))
    raise PermissionDenied("no report access")
