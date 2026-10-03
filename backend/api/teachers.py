from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import SchoolAdminProfile, TeacherProfile


@api_view(["GET", "POST"])
def teacher_collection(request):
    profile = SchoolAdminProfile.objects.filter(user=request.user).first()
    if profile is None:
        return Response({"detail": "Only school admins can manage teachers."}, status=403)
    school_id = profile.school_id
    if request.method == "GET":
        rows = TeacherProfile.objects.filter(school_id=school_id).select_related("user").order_by("id")
        return Response({"results": [
            {"id": t.id, "username": t.user.username, "name": t.user.get_full_name() or t.user.username,
             "staff_id": t.staff_id, "phone": t.phone} for t in rows]})
    d = request.data
    username, password = str(d.get("username", "")).strip(), str(d.get("password", ""))
    if not username or not password:
        return Response({"detail": "Username and password are required."}, status=400)
    if User.objects.filter(username__iexact=username).exists():
        return Response({"detail": "That username is taken."}, status=400)
    try:
        validate_password(password, User(username=username))
    except ValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    with transaction.atomic():
        user = User.objects.create_user(username, password=password,
            first_name=str(d.get("first_name", ""))[:150], last_name=str(d.get("last_name", ""))[:150])
        t = TeacherProfile.objects.create(user=user, school_id=school_id,
            staff_id=str(d.get("staff_id", ""))[:50], phone=str(d.get("phone", ""))[:30])
    return Response({"id": t.id, "username": username}, status=201)
