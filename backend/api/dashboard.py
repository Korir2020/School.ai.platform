from django.db.models import Count
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    Enrollment, Exam, Performance, School, SchoolAdminProfile, Stream,
    Student, Subject, TeacherAssignment, TeacherProfile, Term,
)
from .views import _scope

STATUSES = ("draft", "submitted", "approved", "locked")


def _status_counts(qs):
    counts = {s: 0 for s in STATUSES}
    for row in qs.values("status").annotate(n=Count("id")):
        counts[row["status"]] = row["n"]
    return counts


def _active_term(school_id):
    return (
        Term.objects.filter(academic_year__school_id=school_id, is_active=True)
        .select_related("academic_year").order_by("-start_date").first()
    )


def _term_info(term):
    if term is None:
        return None
    return {"id": term.id, "name": term.name, "academic_year": term.academic_year.name}


def _admin_data(school_id):
    term = _active_term(school_id)
    marks = Performance.objects.filter(student__school_id=school_id)
    exams = {"draft": 0, "published": 0}
    for row in Exam.objects.filter(school_id=school_id).values("status").annotate(n=Count("id")):
        exams[row["status"]] = row["n"]
    return {
        "role": "school_admin",
        "students": Student.objects.filter(school_id=school_id).count(),
        "active_enrollments": Enrollment.objects.filter(
            student__school_id=school_id, is_active=True).count(),
        "teachers": TeacherProfile.objects.filter(school_id=school_id).count(),
        "streams": Stream.objects.filter(school_id=school_id, is_active=True).count(),
        "subjects": Subject.objects.filter(school_id=school_id, is_active=True).count(),
        "active_term": _term_info(term),
        "marks_by_status": _status_counts(marks.filter(term=term) if term else marks.none()),
        "awaiting_approval": marks.filter(status="submitted").count(),
        "exams": exams,
    }


def _teacher_data(user, school_id):
    term = _active_term(school_id)
    mine = Performance.objects.filter(entered_by=user, student__school_id=school_id)
    assignments = TeacherAssignment.objects.filter(
        teacher__user=user, school_id=school_id
    ).select_related("subject", "stream__class_level")
    return {
        "role": "teacher",
        "active_term": _term_info(term),
        "assignments": [
            {
                "id": a.id,
                "subject": a.subject.name,
                "stream": a.stream.name,
                "class_level": a.stream.class_level.name,
            }
            for a in assignments
        ],
        "my_marks_by_status": _status_counts(mine.filter(term=term) if term else mine.none()),
    }


def _superadmin_data():
    schools = School.objects.annotate(
        student_count=Count("student", distinct=True),
        teacher_count=Count("teacher_profiles", distinct=True),
    ).order_by("name")
    return {
        "role": "superadmin",
        "total_schools": schools.count(),
        "schools": [
            {"id": s.id, "name": s.name, "students": s.student_count,
             "teachers": s.teacher_count}
            for s in schools
        ],
    }


@api_view(["GET"])
def dashboard(request):
    school_id, error = _scope(request)
    if error:
        return error
    if request.user.is_superuser:
        return Response(_superadmin_data())
    if SchoolAdminProfile.objects.filter(user=request.user).exists():
        return Response(_admin_data(school_id))
    return Response(_teacher_data(request.user, school_id))
