from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    School, Student, AcademicYear, Term, Curriculum, ClassLevel,
    Stream, Enrollment, Subject, Performance,
)
from .pagination import paginated_response
from .permissions import get_user_school_id, restrict_for_teacher
from schools.models import MarkAuditLog
from .serializers import (
    SchoolSerializer, StudentSerializer, AcademicYearSerializer,
    TermSerializer, CurriculumSerializer, ClassLevelSerializer,
    StreamSerializer, EnrollmentSerializer, SubjectSerializer,
    PerformanceSerializer,
)


def _scope(request):
    """Return (school_id, error). school_id None + no error = superuser."""
    if request.user.is_superuser:
        return None, None
    school_id = get_user_school_id(request.user)
    if school_id is None:
        return None, Response({"detail": "School access not assigned."}, status=403)
    return school_id, None


def _list(request, model, serializer_class, school_field):
    school_id, error = _scope(request)
    if error:
        return error
    queryset = model.objects.all()
    if school_id is not None and school_field:
        queryset = queryset.filter(**{school_field: school_id})
    queryset = restrict_for_teacher(request.user, queryset)
    return paginated_response(request, queryset, serializer_class)


@api_view(["GET"])
def school_list(request):
    return _list(request, School, SchoolSerializer, "id")


@api_view(["GET"])
def student_list(request):
    return _list(request, Student, StudentSerializer, "school_id")


@api_view(["GET"])
def academic_year_list(request):
    return _list(request, AcademicYear, AcademicYearSerializer, "school_id")


@api_view(["GET"])
def term_list(request):
    return _list(request, Term, TermSerializer, "academic_year__school_id")


@api_view(["GET"])
def curriculum_list(request):
    # Shared catalogue: any authenticated user may read it.
    return _list(request, Curriculum, CurriculumSerializer, None)


@api_view(["GET"])
def class_level_list(request):
    # Shared catalogue: any authenticated user may read it.
    return _list(request, ClassLevel, ClassLevelSerializer, None)


@api_view(["GET"])
def stream_list(request):
    return _list(request, Stream, StreamSerializer, "school_id")


@api_view(["GET"])
def enrollment_list(request):
    return _list(request, Enrollment, EnrollmentSerializer, "student__school_id")


@api_view(["GET"])
def subject_list(request):
    return _list(request, Subject, SubjectSerializer, "school_id")


@api_view(["GET", "POST"])
def performance_list(request):
    school_id, error = _scope(request)
    if error:
        return error

    if request.method == "GET":
        queryset = Performance.objects.all()
        if school_id is not None:
            queryset = queryset.filter(student__school_id=school_id)
        queryset = restrict_for_teacher(request.user, queryset)
        return paginated_response(request, queryset, PerformanceSerializer)

    serializer = PerformanceSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data = serializer.validated_data
    if school_id is not None:
        owners = {
            data["student"].school_id,
            data["subject"].school_id,
            data["academic_year"].school_id,
            data["term"].academic_year.school_id,
        }
        if owners != {school_id}:
            return Response(
                {"detail": "Records must belong to your school."}, status=403
            )

    if not request.user.is_superuser:
        from schools.models import SchoolAdminProfile, TeacherAssignment
        is_admin = SchoolAdminProfile.objects.filter(user=request.user).exists()
        if not is_admin:
            enrollment = Enrollment.objects.filter(
                student=data["student"], academic_year=data["academic_year"]
            ).first()
            stream_id = enrollment.stream_id if enrollment else None
            allowed = stream_id is not None and TeacherAssignment.objects.filter(
                teacher__user=request.user,
                subject=data["subject"],
                stream_id=stream_id,
            ).exists()
            if not allowed:
                return Response(
                    {"detail": "You are not assigned to this class and subject."},
                    status=403,
                )

    perf = serializer.save(entered_by=request.user, status="draft")
    MarkAuditLog.objects.create(
        performance=perf, school_id=perf.student.school_id, user=request.user,
        action="created", details={"marks": str(perf.marks)},
    )
    return Response(serializer.data, status=201)
