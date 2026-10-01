from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    AcademicYear, Enrollment, SchoolAdminProfile, Stream, Subject,
    TeacherAssignment, Term,
)
from .serializers import (
    AcademicYearSerializer, EnrollmentSerializer, StreamSerializer,
    SubjectSerializer, TermSerializer,
)
from .views import _list, _scope


class TeacherAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherAssignment
        fields = "__all__"


def _create(request, serializer_class, owners, inject_school=False, check=None):
    school_id, error = _scope(request)
    if error:
        return error
    is_admin = SchoolAdminProfile.objects.filter(user=request.user).exists()
    if not (request.user.is_superuser or is_admin):
        return Response({"detail": "Only school admins can do this."}, status=403)

    data = request.data.copy()
    if inject_school and school_id is not None:
        data["school"] = school_id
    serializer = serializer_class(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    v = serializer.validated_data
    found = {x for x in (o(v) for o in owners) if x is not None}
    if school_id is not None:
        if found - {school_id}:
            return Response({"detail": "Records must belong to your school."}, status=403)
    elif len(found) > 1:
        return Response({"detail": "Linked records must belong to the same school."}, status=400)

    if check:
        problem = check(v)
        if problem:
            return Response({"detail": problem}, status=400)
    obj = serializer.save()
    return Response(serializer_class(obj).data, status=201)


def _dates(v):
    if v["start_date"] > v["end_date"]:
        return "End date must not be before start date."


def _term_check(v):
    bad = _dates(v)
    if bad:
        return bad
    y = v["academic_year"]
    if v["start_date"] < y.start_date or v["end_date"] > y.end_date:
        return "Term dates must fall inside the academic year."


def _enrollment_check(v):
    stream = v.get("stream")
    if stream and stream.class_level_id != v["class_level"].id:
        return "Stream does not belong to this class level."
    if Enrollment.objects.filter(
        student=v["student"], academic_year=v["academic_year"], is_active=True
    ).exists():
        return "Student is already enrolled for this academic year."


def _assignment_check(v):
    if TeacherAssignment.objects.filter(
        teacher=v["teacher"], subject=v["subject"], stream=v["stream"]
    ).exists():
        return "This assignment already exists."


def _sid(name):
    return lambda v: v[name].school_id if v.get(name) else None


@api_view(["GET", "POST"])
def academic_year_collection(request):
    if request.method == "GET":
        return _list(request, AcademicYear, AcademicYearSerializer, "school_id")
    return _create(request, AcademicYearSerializer, [lambda v: v["school"].id],
                   inject_school=True, check=_dates)


@api_view(["GET", "POST"])
def term_collection(request):
    if request.method == "GET":
        return _list(request, Term, TermSerializer, "academic_year__school_id")
    return _create(request, TermSerializer, [_sid("academic_year")], check=_term_check)


@api_view(["GET", "POST"])
def stream_collection(request):
    if request.method == "GET":
        return _list(request, Stream, StreamSerializer, "school_id")
    return _create(request, StreamSerializer, [lambda v: v["school"].id], inject_school=True)


@api_view(["GET", "POST"])
def subject_collection(request):
    if request.method == "GET":
        return _list(request, Subject, SubjectSerializer, "school_id")
    return _create(request, SubjectSerializer, [lambda v: v["school"].id], inject_school=True)


@api_view(["GET", "POST"])
def enrollment_collection(request):
    if request.method == "GET":
        return _list(request, Enrollment, EnrollmentSerializer, "student__school_id")
    return _create(
        request, EnrollmentSerializer,
        [_sid("student"), _sid("academic_year"), _sid("stream")],
        check=_enrollment_check,
    )


@api_view(["GET", "POST"])
def teacher_assignment_collection(request):
    if request.method == "GET":
        return _list(request, TeacherAssignment, TeacherAssignmentSerializer, "school_id")
    return _create(
        request, TeacherAssignmentSerializer,
        [lambda v: v["school"].id, _sid("teacher"), _sid("subject"), _sid("stream")],
        inject_school=True, check=_assignment_check,
    )
