from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Exam, SchoolAdminProfile
from .views import _scope


class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = (
            "id", "school", "name", "term", "assessment_type",
            "class_level", "status", "published_at",
        )
        read_only_fields = ("school", "status", "published_at")


@api_view(["GET", "POST"])
def exam_list(request):
    school_id, error = _scope(request)
    if error:
        return error

    if request.method == "GET":
        exams = Exam.objects.all()
        if school_id is not None:
            exams = exams.filter(school_id=school_id)
        term_id = request.query_params.get("term")
        if term_id and term_id.isdigit():
            exams = exams.filter(term_id=int(term_id))
        return Response(ExamSerializer(exams, many=True).data)

    if not request.user.is_superuser and not SchoolAdminProfile.objects.filter(
        user=request.user
    ).exists():
        return Response({"detail": "Admins only."}, status=403)

    serializer = ExamSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    term_school_id = serializer.validated_data["term"].academic_year.school_id
    if school_id is not None and term_school_id != school_id:
        return Response({"detail": "Term must belong to your school."}, status=403)
    serializer.save(school_id=term_school_id)
    return Response(serializer.data, status=201)
