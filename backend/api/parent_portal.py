from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F, Prefetch, Sum
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import (
    FeePayment, GuardianProfile, SchoolAdminProfile, Student, StudentFee,
    StudentGuardian, Term,
)
from .views import _scope


def _parent(request):
    profile = GuardianProfile.objects.filter(user=request.user).first()
    if not profile:
        return None, Response({"detail": "Parent access not assigned."}, status=403)
    return profile, None


def _child(x):
    prefetched = getattr(x, "_prefetched_objects_cache", {}).get("fees")
    if prefetched is None:
        totals = StudentFee.objects.filter(student=x).aggregate(
            due=Sum("amount_due"), paid=Sum("amount_paid"),
        )
        due, paid = totals["due"] or 0, totals["paid"] or 0
    else:
        due = sum((fee.amount_due for fee in prefetched), 0)
        paid = sum((fee.amount_paid for fee in prefetched), 0)
    return {"id": x.id, "name": str(x), "admission_number": x.admission_number,
            "date_of_birth": x.date_of_birth,
            "fees": {"due": str(due), "paid": str(paid),
                     "balance": str(due - paid)}}


@api_view(["GET"])
def parent_children(request):
    profile, error = _parent(request)
    if error:
        return error
    children = Student.objects.filter(
        guardians__guardian=profile, school_id=profile.school_id,
    ).distinct().order_by("last_name", "first_name", "id").prefetch_related(
        Prefetch("fees", queryset=StudentFee.objects.only(
            "student_id", "amount_due", "amount_paid",
        )),
    )
    terms = Term.objects.filter(academic_year__school_id=profile.school_id).select_related(
        "academic_year").order_by("-start_date")
    return Response({"children": [_child(x) for x in children], "terms": [
        {"id": t.id, "name": t.name, "academic_year": t.academic_year.name}
        for t in terms]})


@api_view(["GET"])
def parent_fees(request, student_id):
    profile, error = _parent(request)
    if error:
        return error
    if not StudentGuardian.objects.filter(
        guardian=profile, student_id=student_id,
        student__school_id=profile.school_id,
    ).exists():
        return Response({"detail": "Not found."}, status=404)
    rows = StudentFee.objects.filter(
        student_id=student_id, student__school_id=profile.school_id,
    ).select_related("fee_structure")
    return Response([{"id": x.id, "fee": x.fee_structure.name,
                      "amount_due": str(x.amount_due), "amount_paid": str(x.amount_paid),
                      "balance": str(x.balance), "status": x.status,
                      "due_date": x.fee_structure.due_date} for x in rows])


@api_view(["GET", "POST"])
def parent_accounts(request):
    school_id, error = _scope(request)
    if error:
        return error
    if not request.user.is_superuser and not SchoolAdminProfile.objects.filter(user=request.user).exists():
        return Response({"detail": "Only school admins can manage parents."}, status=403)
    if request.method == "GET":
        rows = list(GuardianProfile.objects.filter(
            school_id=school_id,
        ).select_related("user"))
        linked = StudentGuardian.objects.filter(
            guardian_id__in=[row.id for row in rows],
            student__school_id=F("guardian__school_id"),
        ).values_list("guardian_id", "student_id")
        students_by_guardian = {}
        for guardian_id, student_id in linked:
            students_by_guardian.setdefault(guardian_id, []).append(student_id)
        return Response([{"id": x.id, "username": x.user.username,
                          "students": students_by_guardian.get(x.id, [])}
                         for x in rows])
    data = request.data
    students = Student.objects.filter(id__in=data.get("student_ids", []))
    if school_id is not None and students.exclude(school_id=school_id).exists():
        return Response({"detail": "Students must belong to your school."}, status=403)
    if not data.get("username") or not data.get("password") or not students.exists():
        return Response({"detail": "Username, password, and at least one student are required."}, status=400)
    if school_id is None and students.exclude(school_id=students.order_by("id").values_list("school_id", flat=True).first()).exists():
        return Response({"detail": "A guardian account cannot link students from multiple schools."}, status=400)
    if User.objects.filter(username=data["username"]).exists():
        return Response({"detail": "Username already exists."}, status=400)
    with transaction.atomic():
        user = User.objects.create_user(username=data["username"], password=data["password"],
                                        first_name=data.get("first_name", ""), last_name=data.get("last_name", ""))
        guardian = GuardianProfile.objects.create(user=user, school_id=school_id or students.first().school_id,
                                                  phone=data.get("phone", ""))
        StudentGuardian.objects.bulk_create([
            StudentGuardian(student=s, guardian=guardian, relationship=data.get("relationship", ""))
            for s in students])
    return Response({"id": guardian.id, "username": user.username,
                     "students": list(students.values_list("id", flat=True))}, status=201)
