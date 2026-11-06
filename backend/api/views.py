from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    School, Student, AcademicYear, Term, Curriculum, ClassLevel,
    Stream, Enrollment, Subject, SubjectDefinition, Performance,
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
    if model is Stream:
        queryset = queryset.select_related("class_level")
    elif model is Subject:
        queryset = queryset.select_related("definition__curriculum")
    queryset = restrict_for_teacher(request.user, queryset)
    return paginated_response(request, queryset, serializer_class)


@api_view(["GET", "POST"])
def school_list(request):
    if request.method == "POST":
        from .school_create import create_school
        return create_school(request)
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
def primary_subject_catalog(request):
    """CBC Primary learning-area catalogue scoped to one Grade 1–6 level."""
    try:
        level_id = int(request.query_params.get("class_level", ""))
    except (TypeError, ValueError):
        return Response({"detail": "Choose a CBC Primary class level."}, status=400)
    level = ClassLevel.objects.select_related("curriculum").filter(
        pk=level_id, curriculum__code__iexact="CBC", level_number__gte=1,
        level_number__lte=6, is_active=True,
    ).first()
    if level is None:
        return Response({"detail": "Not found: CBC Primary class level."}, status=404)
    rows = SubjectDefinition.objects.filter(
        curriculum=level.curriculum, is_active=True,
        class_levels=level,
    ).order_by("name", "code")
    return Response([{"id": row.id, "name": row.name, "code": row.code,
                      "class_level_id": level.id, "class_level_name": level.name}
                     for row in rows])


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
        for parameter, field in (
            ("term", "term_id"), ("academic_year", "academic_year_id"),
            ("subject", "subject_id"), ("student", "student_id"),
            ("paper_number", "paper_number"),
            ("class_level", "student__enrollment__class_level_id"),
            ("stream", "student__enrollment__stream_id"),
        ):
            value = request.query_params.get(parameter)
            if value is None:
                continue
            try:
                numeric = int(value)
            except (TypeError, ValueError):
                return Response({"detail": f"Invalid {parameter} filter."}, status=400)
            if numeric <= 0:
                return Response({"detail": f"Invalid {parameter} filter."}, status=400)
            queryset = queryset.filter(**{field: numeric})
        if request.query_params.get("class_level") or request.query_params.get("stream"):
            queryset = queryset.filter(student__enrollment__is_active=True).distinct()
        assessment_type = request.query_params.get("assessment_type")
        if assessment_type:
            if assessment_type not in {"opener", "mid", "end"}:
                return Response({"detail": "Invalid assessment_type filter."}, status=400)
            queryset = queryset.filter(assessment_type=assessment_type)
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in {"draft", "submitted", "approved", "locked"}:
                return Response({"detail": "Invalid status filter."}, status=400)
            queryset = queryset.filter(status=status_filter)
        return paginated_response(request, queryset, PerformanceSerializer)

    if school_id is not None:
        references = (
            ("student", Student, lambda row: row.school_id),
            ("subject", Subject, lambda row: row.school_id),
            ("academic_year", AcademicYear, lambda row: row.school_id),
            ("term", Term, lambda row: row.academic_year.school_id),
        )
        for field, model, school_for in references:
            try:
                ref_id = int(request.data.get(field))
            except (TypeError, ValueError):
                continue
            if ref_id > 0:
                ref = model.objects.filter(pk=ref_id).select_related(
                    "academic_year" if field == "term" else None
                ).first()
                if ref is not None and school_for(ref) != school_id:
                    return Response(
                        {"detail": "Records must belong to your school."}, status=403
                    )

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
        action="created", details={
            "marks": str(perf.marks) if perf.marks is not None else None,
            "mark_status": perf.mark_status,
            "workflow_status": perf.status,
            "student_id": perf.student_id, "subject_id": perf.subject_id,
            "academic_year_id": perf.academic_year_id,
            "term_id": perf.term_id, "paper_number": perf.paper_number,
        },
    )
    return Response(serializer.data, status=201)
