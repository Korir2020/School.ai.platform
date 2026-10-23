from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    GuardianProfile, SchoolAdminProfile, StaffProfile, TeacherProfile)


@api_view(["GET"])
def me(request):
    user = request.user
    role, school, is_deputy = "none", None, False
    if user.is_superuser:
        role = "superadmin"
    else:
        admin = SchoolAdminProfile.objects.select_related("school").filter(user=user).first()
        teacher = TeacherProfile.objects.select_related("school").filter(user=user).first()
        if admin:
            role, school, is_deputy = "school_admin", admin.school, admin.is_deputy
        elif teacher:
            role, school = "teacher", teacher.school
        else:
            staff = StaffProfile.objects.select_related(
                "school").filter(user=user).first()
            if staff:
                role, school = staff.role, staff.school
            else:
                guardian = GuardianProfile.objects.select_related(
                    "school").filter(user=user).first()
                if guardian:
                    role, school = "parent", guardian.school
    from schools.models import ClassTeacher
    is_ct = role == "teacher" and ClassTeacher.objects.filter(teacher__user=user).exists()
    return Response({
        "username": user.username,
        "role": role,
        "is_deputy": is_deputy,
        "is_class_teacher": is_ct,
        "school": {"id": school.id, "name": school.name} if school else None,
        "setup_complete": (school.setup_completed_at is not None) if school else None,
    })
