from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import SchoolAdminProfile, TeacherProfile


@api_view(["GET"])
def me(request):
    user = request.user
    role, school = "none", None
    if user.is_superuser:
        role = "superadmin"
    else:
        admin = SchoolAdminProfile.objects.select_related("school").filter(user=user).first()
        teacher = TeacherProfile.objects.select_related("school").filter(user=user).first()
        if admin:
            role, school = "school_admin", admin.school
        elif teacher:
            role, school = "teacher", teacher.school
    return Response({
        "username": user.username,
        "role": role,
        "school": {"id": school.id, "name": school.name} if school else None,
    })
