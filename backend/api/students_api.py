from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import SchoolAdminProfile, Student
from .serializers import StudentSerializer
from .views import _scope, student_list


@api_view(["GET", "POST"])
def student_collection(request):
    if request.method == "GET":
        return student_list._wrapped_view(request) if False else student_list.cls.as_view()(request._request)

    school_id, error = _scope(request)
    if error:
        return error
    is_admin = SchoolAdminProfile.objects.filter(user=request.user).exists()
    if not (request.user.is_superuser or is_admin):
        return Response({"detail": "Only school admins can add students."}, status=403)

    data = request.data.copy()
    if school_id is not None:
        data["school"] = school_id  # admins can only add to their own school

    serializer = StudentSerializer(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    student = serializer.save()
    return Response(StudentSerializer(student).data, status=201)
