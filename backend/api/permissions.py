from rest_framework.permissions import BasePermission
from schools.models import SchoolAdminProfile, TeacherProfile


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsSchoolAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return SchoolAdminProfile.objects.filter(user=request.user).exists()


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return TeacherProfile.objects.filter(user=request.user).exists()


def get_user_school_id(user):
    """Return the user's school id, or None if they have no school.
    Superusers are handled separately by callers (they see all schools)."""
    if not user or not user.is_authenticated:
        return None
    profile = SchoolAdminProfile.objects.filter(user=user).first()
    if profile:
        return profile.school_id
    profile = TeacherProfile.objects.filter(user=user).first()
    if profile:
        return profile.school_id
    return None
