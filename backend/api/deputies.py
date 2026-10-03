from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import SchoolAdminProfile

NO = "Only the school administrator can manage deputies."


def _boss(request):
    return SchoolAdminProfile.objects.filter(user=request.user, is_deputy=False).first()


@api_view(["GET", "POST"])
def deputy_collection(request):
    boss = _boss(request)
    if boss is None:
        return Response({"detail": NO}, status=403)
    if request.method == "GET":
        rows = SchoolAdminProfile.objects.filter(
            school_id=boss.school_id, is_deputy=True).select_related("user").order_by("id")
        return Response({"results": [{"id": p.id, "username": p.user.username,
            "name": p.user.get_full_name() or p.user.username} for p in rows]})
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
        p = SchoolAdminProfile.objects.create(user=user, school_id=boss.school_id, is_deputy=True)
    return Response({"id": p.id, "username": username}, status=201)


@api_view(["DELETE"])
def deputy_detail(request, pk):
    boss = _boss(request)
    if boss is None:
        return Response({"detail": NO}, status=403)
    p = SchoolAdminProfile.objects.filter(
        pk=pk, school_id=boss.school_id, is_deputy=True).select_related("user").first()
    if p is None:
        return Response({"detail": "Not found."}, status=404)
    user = p.user
    with transaction.atomic():
        p.delete()
        user.is_active = False
        user.save()
    return Response(status=204)
