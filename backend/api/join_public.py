from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from schools.models import JoinRequest, MarkAuditLog, School
from .join_throttle import JoinRegisterThrottle
from .notify import notify_admins

ROLES = {r for r, _ in JoinRequest.ROLES}


def _bad(text, code=400):
    return Response({"detail": text}, status=code)


def _school(code):
    rows = School.objects.filter(code__iexact=code)
    return rows.first() if rows.count() == 1 else None


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([JoinRegisterThrottle])
def join_register(request):
    d = request.data
    username = str(d.get("username", "")).strip()
    password = str(d.get("password", ""))
    role = str(d.get("role", "")).strip().lower()
    code = str(d.get("school_code", "")).strip()
    if not username or not password or not code:
        return _bad("Username, password and school code are required.")
    if role not in ROLES:
        return _bad("Choose Teacher, Bursar or Secretary.")
    school = _school(code)
    if school is None:
        return _bad("School code not found.", 404)
    if User.objects.filter(username__iexact=username).exists():
        return _bad("That username is taken.")
    try:
        validate_password(password, User(username=username))
    except ValidationError as e:
        return _bad(" ".join(e.messages))
    with transaction.atomic():
        user = User.objects.create_user(
            username, password=password,
            first_name=str(d.get("first_name", ""))[:150],
            last_name=str(d.get("last_name", ""))[:150])
        jr = JoinRequest.objects.create(
            user=user, school=school, role=role)
        MarkAuditLog.objects.create(
            school=school, user=user, action="join_requested",
            details={"username": username, "role": role})
        who = user.get_full_name() or username
        notify_admins(
            school, "join_requested",
            f"{who} asked to join as {role}.", jr)
    return Response({"status": "pending", "school": school.name,
                     "detail": "Request sent to the school administrator."},
                    status=201)
