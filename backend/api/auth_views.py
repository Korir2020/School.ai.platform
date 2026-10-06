from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    SchoolAdminProfile, StaffProfile, TeacherProfile)


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
    return Response({
        "username": user.username,
        "role": role,
        "is_deputy": is_deputy,
        "school": {"id": school.id, "name": school.name} if school else None,
    })
