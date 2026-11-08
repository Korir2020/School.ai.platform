from django.db import transaction
from django.db.models import ProtectedError
from rest_framework.decorators import api_view
from api.fee_permissions import get_fee_access_school_id
from rest_framework.response import Response

from schools.models import (
    AcademicYear, ClassTeacher, Enrollment, LevelResult, Performance,
    SchoolAdminProfile, StaffProfile, Stream, Student, Subject, SubjectPaper,
    SubjectRegistration, TeacherAssignment, Term,
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


def _confirmed(request):
    value = request.data.get("confirm") if hasattr(request, "data") else None
    if value is None:
        value = request.query_params.get("confirm")
    return str(value).lower() in {"1", "true", "yes"}


def _stream_impact(stream):
    return {
        "learners_affected": Enrollment.objects.filter(stream=stream).values("student_id").distinct().count(),
        "enrollments_unlinked": Enrollment.objects.filter(stream=stream).count(),
        "marks_affected": 0,
        "teacher_assignments_removed": TeacherAssignment.objects.filter(stream=stream).count(),
        "class_teacher_records_removed": ClassTeacher.objects.filter(stream=stream).count(),
        "enrollment_rule": "Enrollment.stream is SET_NULL; learner and enrollment records remain.",
    }


def _subject_impact(subject):
    performance_students = set(
        Performance.objects.filter(subject=subject).values_list("student_id", flat=True)
    )
    level_students = set(
        LevelResult.objects.filter(subject=subject).values_list("student_id", flat=True)
    )
    registration_students = set(
        SubjectRegistration.objects.filter(subject=subject).values_list("student_id", flat=True)
    )
    return {
        "learners_affected": len(performance_students | level_students | registration_students),
        "marks_affected": Performance.objects.filter(subject=subject).count(),
        "level_results_affected": LevelResult.objects.filter(subject=subject).count(),
        "subject_registrations_blocking": len(registration_students),
        "papers_removed": SubjectPaper.objects.filter(subject=subject).count(),
        "teacher_assignments_removed": TeacherAssignment.objects.filter(subject=subject).count(),
        "marks_rule": "Performance and LevelResult rows CASCADE; they are not deleted without confirmation.",
        "registration_rule": "SubjectRegistration is PROTECT; a subject with registrations cannot be deleted.",
    }


def _delete_prompt(label, impact):
    return Response({
        "detail": f"Deleting this {label} needs explicit confirmation after reviewing its impact.",
        "impact": impact,
        "requires_confirmation": True,
    }, status=409)


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
    from rest_framework.response import Response
    old = None
    fee_school_id = None
    if request.method == "PATCH" and "fee_category" in request.data:
        school_id = Student.objects.filter(pk=pk).values_list("school_id", flat=True).first()
        if school_id is not None:
            fee_school_id = get_fee_access_school_id(request.user, school_id=school_id)
        else:
            fee_school_id = get_fee_access_school_id(request.user)
        value = str(request.data.get("fee_category") or "").strip().lower()
        if value not in ("day", "boarder"):
            return Response({"detail": "Category must be day or boarder."}, status=400)
        old = Student.objects.filter(pk=pk).values_list("fee_category", flat=True).first()
        is_admin = request.user.is_superuser or SchoolAdminProfile.objects.filter(
            user=request.user).exists()
        is_bursar = StaffProfile.objects.filter(user=request.user, role="bursar").exists()
        if not is_admin and is_bursar and set(request.data.keys()) <= {"fee_category"}:
            st = Student.objects.filter(pk=pk, school_id=fee_school_id).first()
            if st is None:
                return Response({"detail": "Not found."}, status=404)
            st.fee_category = value
            st.save(update_fields=["fee_category"])
            from api.fee_billing import bill_student, drop_other_category_bills
            if st.fee_category != old:
                drop_other_category_bills(st)
            bill_student(st)
            return Response(StudentSerializer(st).data)
    resp = _detail(request, pk, Student, StudentSerializer, "school_id",
                   {"first_name", "last_name", "admission_number", "date_of_birth", "fee_category"})
    if old is not None and resp.status_code == 200:
        from api.fee_billing import bill_student, drop_other_category_bills
        st = Student.objects.filter(pk=pk).first()
        if st:
            if st.fee_category != old:
                drop_other_category_bills(st)
            bill_student(st)
    return resp


@api_view(["GET", "PATCH"])
def academic_year_detail(request, pk):
    return _detail(request, pk, AcademicYear, AcademicYearSerializer, "school_id",
                   {"name", "start_date", "end_date", "is_active"}, _year_check)


@api_view(["GET", "PATCH"])
def term_detail(request, pk):
    return _detail(request, pk, Term, TermSerializer, "academic_year__school_id",
                   {"name", "start_date", "end_date", "is_active"}, _term_check)


@api_view(["GET", "PATCH", "DELETE"])
def stream_detail(request, pk):
    if request.method == "DELETE":
        if not _is_admin(request.user):
            return Response({"detail": "Only school admins can do this."}, status=403)
        obj, error = _find(request, pk, Stream, "school_id")
        if error:
            return error
        impact = _stream_impact(obj)
        if not _confirmed(request):
            return _delete_prompt("stream", impact)
        with transaction.atomic():
            obj.delete()
        return Response(status=204)
    return _detail(request, pk, Stream, StreamSerializer, "school_id",
                   {"name", "is_active"})


@api_view(["GET", "PATCH", "DELETE"])
def subject_detail(request, pk):
    if request.method == "DELETE":
        if not _is_admin(request.user):
            return Response({"detail": "Only school admins can do this."}, status=403)
        obj, error = _find(request, pk, Subject, "school_id")
        if error:
            return error
        impact = _subject_impact(obj)
        if impact["subject_registrations_blocking"]:
            return Response({
                "detail": "This subject cannot be deleted because learners have subject registrations for it.",
                "impact": impact,
                "blocked": True,
            }, status=409)
        if not _confirmed(request):
            return _delete_prompt("subject", impact)
        try:
            with transaction.atomic():
                obj.delete()
        except ProtectedError:
            return Response({
                "detail": "This subject cannot be deleted because it is still referenced by a protected record.",
                "impact": _subject_impact(obj),
                "blocked": True,
            }, status=409)
        return Response(status=204)
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
