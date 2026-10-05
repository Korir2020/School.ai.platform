from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    School, SchoolAdminProfile, Student, Subject, TeacherProfile,
)
from .permissions import restrict_for_teacher
from .views import _scope

LIMIT = 5


def _words(q):
    return [w for w in q.split() if w]


@api_view(["GET"])
def search(request):
    out = {"students": [], "teachers": [], "subjects": [], "schools": []}
    q = str(request.query_params.get("q", "")).strip()[:60]
    if len(q) < 2:
        return Response(out)
    school_id, error = _scope(request)
    if error:
        return error
    words = _words(q)

    students = Student.objects.all()
    if school_id is not None:
        students = students.filter(school_id=school_id)
    students = restrict_for_teacher(request.user, students)
    for w in words:  # every word must match name or admission number
        students = students.filter(
            Q(first_name__icontains=w) | Q(last_name__icontains=w)
            | Q(admission_number__icontains=w))
    out["students"] = [
        {"id": s.id, "name": s.first_name + " " + s.last_name,
         "admission_number": s.admission_number}
        for s in students.order_by("first_name", "last_name")[:LIMIT]]

    subjects = Subject.objects.filter(is_active=True, name__icontains=q)
    if school_id is not None:
        subjects = subjects.filter(school_id=school_id)
    subjects = restrict_for_teacher(request.user, subjects)
    out["subjects"] = [{"id": s.id, "name": s.name}
                       for s in subjects.order_by("name")[:LIMIT]]

    is_admin = school_id is not None and SchoolAdminProfile.objects.filter(
        user=request.user).exists()
    if is_admin:
        teachers = TeacherProfile.objects.filter(
            school_id=school_id).select_related("user")
        for w in words:
            teachers = teachers.filter(
                Q(user__first_name__icontains=w)
                | Q(user__last_name__icontains=w)
                | Q(user__username__icontains=w))
        out["teachers"] = [
            {"id": t.id, "name": t.user.get_full_name() or t.user.username,
             "username": t.user.username}
            for t in teachers.order_by("user__username")[:LIMIT]]

    if request.user.is_superuser:
        out["schools"] = [
            {"id": s.id, "name": s.name, "code": s.code}
            for s in School.objects.filter(
                Q(name__icontains=q) | Q(code__icontains=q)).order_by("name")[:LIMIT]]
    return Response(out)
