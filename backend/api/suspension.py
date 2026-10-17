from schools.models import GuardianProfile, SchoolAdminProfile, StaffProfile, TeacherProfile

MESSAGE = "This school's account is suspended. Contact Marian support."


def school_for_user(user):
    """The school a non-superuser belongs to, or None."""
    if user is None or not user.is_authenticated or user.is_superuser:
        return None
    for model in (SchoolAdminProfile, TeacherProfile, StaffProfile, GuardianProfile):
        profile = model.objects.select_related("school").filter(user=user).first()
        if profile:
            return profile.school
    return None


def suspended_school_for(user):
    school = school_for_user(user)
    return school if school is not None and school.is_suspended else None


from rest_framework.permissions import BasePermission


class SchoolNotSuspended(BasePermission):
    message = MESSAGE

    def has_permission(self, request, view):
        return suspended_school_for(request.user) is None
