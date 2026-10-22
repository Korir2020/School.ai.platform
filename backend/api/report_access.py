"""Map a logged-in Marian user to a marian_reports User.

Identity comes ONLY from the login, never from request parameters.
Roles follow api/permissions.py: SchoolAdminProfile -> admin,
GuardianProfile -> guardian. Teachers are denied.
Superusers have no school, so report access is denied for them.
Policy: teachers only upload marks; reports belong to administrators
and deputies, so a teacher login is denied here.
"""
from marian_reports.domain import PermissionDenied, User

from schools.models import (
    GuardianProfile, SchoolAdminProfile, StudentGuardian,
    TeacherProfile,
)


def build_report_user(user):
    if user is None or not getattr(user, "is_authenticated", False) \
            or user.is_superuser:
        raise PermissionDenied("no report access")
    uid = str(user.pk)
    admin = SchoolAdminProfile.objects.filter(user=user).first()
    if admin:
        return User(uid, str(admin.school_id), "admin", can_view_fees=True)
    if TeacherProfile.objects.filter(user=user).exists():
        raise PermissionDenied('teachers do not open reports')
    guardian = GuardianProfile.objects.filter(user=user).first()
    if guardian:
        ids = StudentGuardian.objects.filter(
            guardian=guardian, student__school_id=guardian.school_id,
        ).values_list("student_id", flat=True)
        return User(uid, str(guardian.school_id), "guardian",
                    student_ids=tuple(sorted(str(i) for i in ids)))
    raise PermissionDenied("no report access")
