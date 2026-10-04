from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    AcademicYear, Enrollment, SchoolAdminProfile, Stream, Student, Subject,
    TeacherAssignment, Term,
)
from .admin_create import TeacherAssignmentSerializer
from .serializers import (
    AcademicYearSerializer, EnrollmentSerializer, StreamSerializer,
    StudentSerializer, SubjectSerializer, TermSerializer,
)
from .permissions import restrict_for_teacher
from .views import _scope


def _find(request, pk, model, school_path):
    school_id, error = _scope(request)
    if error:
        return None, error
    qs = model.objects.all()
    if school_id is not None:
        qs = qs.filter(**{school_path: school_id})
    qs = restrict_for_teacher(request.user, qs)
    obj = qs.filter(pk=pk).first()
    if obj is None:
        return None, Response({"detail": "Not found."}, status=404)
    return obj, None


def _is_admin(user):
    return user.is_superuser or SchoolAdminProfile.objects.filter(user=user).exists()


def _detail(request, pk, model, serializer_class, school_path, fields, check=None):
    if request.method != "GET" and not _is_admin(request.user):
        return Response({"detail": "Only school admins can do this."}, status=403)
    obj, error = _find(request, pk, model, school_path)
    if error:
        return error
    if request.method == "GET":
        return Response(serializer_class(obj).data)

    data = {k: v for k, v in request.data.items() if k in fields}
    if not data:
        return Response({"detail": "No editable fields supplied."}, status=400)
    serializer = serializer_class(obj, data=data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    if check:
        problem = check(obj, serializer.validated_data)
        if problem:
            return Response({"detail": problem}, status=400)
    serializer.save()
    return Response(serializer.data)


def _m(obj, v, key):
    return v[key] if key in v else getattr(obj, key)


def _dates(obj, v):
    if _m(obj, v, "start_date") > _m(obj, v, "end_date"):
        return "End date must not be before start date."


def _year_check(obj, v):
    bad = _dates(obj, v)
    if bad:
        return bad
    s, e = _m(obj, v, "start_date"), _m(obj, v, "end_date")
    if obj.term_set.exclude(start_date__gte=s, end_date__lte=e).exists():
        return "Existing terms fall outside the new dates."


def _term_check(obj, v):
    bad = _dates(obj, v)
    if bad:
        return bad
    y = obj.academic_year
    if _m(obj, v, "start_date") < y.start_date or _m(obj, v, "end_date") > y.end_date:
        return "Term dates must fall inside the academic year."


def _enrollment_check(obj, v):
    stream = v.get("stream")
    if "stream" in v and stream is not None:
        if stream.school_id != obj.student.school_id:
            return "Stream must belong to the student's school."
        if stream.class_level_id != obj.class_level_id:
            return "Stream does not belong to this class level."
    if v.get("is_active") and Enrollment.objects.filter(
        student=obj.student, academic_year=obj.academic_year, is_active=True
    ).exclude(pk=obj.pk).exists():
        return "Student is already enrolled for this academic year."


@api_view(["GET", "PATCH"])
def student_detail(request, pk):
    return _detail(request, pk, Student, StudentSerializer, "school_id",
                   {"first_name", "last_name", "admission_number", "date_of_birth"})


@api_view(["GET", "PATCH"])
def academic_year_detail(request, pk):
    return _detail(request, pk, AcademicYear, AcademicYearSerializer, "school_id",
                   {"name", "start_date", "end_date", "is_active"}, _year_check)


@api_view(["GET", "PATCH"])
def term_detail(request, pk):
    return _detail(request, pk, Term, TermSerializer, "academic_year__school_id",
                   {"name", "start_date", "end_date", "is_active"}, _term_check)


@api_view(["GET", "PATCH"])
def stream_detail(request, pk):
    return _detail(request, pk, Stream, StreamSerializer, "school_id",
                   {"name", "is_active"})


@api_view(["GET", "PATCH"])
def subject_detail(request, pk):
    return _detail(request, pk, Subject, SubjectSerializer, "school_id",
                   {"name", "code", "is_active"})


@api_view(["GET", "PATCH"])
def enrollment_detail(request, pk):
    return _detail(request, pk, Enrollment, EnrollmentSerializer,
                   "student__school_id", {"stream", "is_active"}, _enrollment_check)


@api_view(["GET", "DELETE"])
def teacher_assignment_detail(request, pk):
    if request.method == "DELETE" and not _is_admin(request.user):
        return Response({"detail": "Only school admins can do this."}, status=403)
    obj, error = _find(request, pk, TeacherAssignment, "school_id")
    if error:
        return error
    if request.method == "GET":
        return Response(TeacherAssignmentSerializer(obj).data)
    obj.delete()
    return Response(status=204)
