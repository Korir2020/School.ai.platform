from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.response import Response
from schools.models import MarkAuditLog, School, SchoolAdminProfile

def create_school(request):
    if not request.user.is_superuser:
        return Response({"detail": "Only a superuser can create schools."}, status=403)
    d = request.data
    name, code = str(d.get("name", "")).strip(), str(d.get("code", "")).strip()
    username, password = str(d.get("admin_username", "")).strip(), str(d.get("admin_password", ""))
    if not (name and code and username and password):
        return Response({"detail": "Name, code, admin username and admin password are required."}, status=400)
    if School.objects.filter(code__iexact=code).exists():
        return Response({"detail": "That school code is taken."}, status=400)
    if User.objects.filter(username__iexact=username).exists():
        return Response({"detail": "That username is taken."}, status=400)
    try:
        validate_password(password, User(username=username))
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    with transaction.atomic():
        school = School.objects.create(
            name=name[:200], code=code[:50],
            location=str(d.get("location", ""))[:200],
            email=str(d.get("email", ""))[:254],
            phone=str(d.get("phone", ""))[:30])
        user = User.objects.create_user(
            username, password=password,
            first_name=str(d.get("admin_first_name", ""))[:150],
            last_name=str(d.get("admin_last_name", ""))[:150])
        SchoolAdminProfile.objects.create(user=user, school=school, is_deputy=False)
        MarkAuditLog.objects.create(
            school=school, user=request.user, action="school_created",
            details={"school_id": school.id, "admin_username": username})
    return Response({"id": school.id, "name": school.name, "code": school.code,
                     "admin_username": username}, status=201)
