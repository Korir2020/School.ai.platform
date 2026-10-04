from rest_framework.permissions import BasePermission
from schools.models import SchoolAdminProfile, TeacherProfile


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsSchoolAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return SchoolAdminProfile.objects.filter(user=request.user).exists()


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return TeacherProfile.objects.filter(user=request.user).exists()


def get_user_school_id(user):
    """Return the user's school id, or None if they have no school.
    Superusers are handled separately by callers (they see all schools)."""
    if not user or not user.is_authenticated:
        return None
    profile = SchoolAdminProfile.objects.filter(user=user).first()
    if profile:
        return profile.school_id
    profile = TeacherProfile.objects.filter(user=user).first()
    if profile:
        return profile.school_id
    return None


def is_teacher_only(user):
    if not user or not user.is_authenticated or user.is_superuser:
        return False
    if SchoolAdminProfile.objects.filter(user=user).exists():
        return False
    return TeacherProfile.objects.filter(user=user).exists()


def restrict_for_teacher(user, qs):
    """Plain teachers see only their own classes. Others unchanged."""
    if not is_teacher_only(user):
        return qs
    from django.db.models import Q
    from schools.models import (
        Enrollment, Performance, Student, Subject, TeacherAssignment,
    )
    rows = TeacherAssignment.objects.filter(teacher__user=user)
    mine = list(rows.values_list("subject_id", "stream_id"))
    streams = {st for _, st in mine}
    m = qs.model
    if m is TeacherAssignment:
        return qs.filter(teacher__user=user)
    if m is Subject:
        return qs.filter(id__in={s for s, _ in mine})
    if m is Enrollment:
        return qs.filter(stream_id__in=streams)
    if m is Student:
        return qs.filter(enrollment__stream_id__in=streams).distinct()
    if m is Performance:
        q = Q(pk__in=[])
        for subj, st in mine:
            q |= Q(subject_id=subj, student__enrollment__stream_id=st)
        return qs.filter(q).distinct()
    return qs
