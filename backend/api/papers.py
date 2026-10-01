from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import SchoolAdminProfile, SubjectPaper
from .views import _scope


class SubjectPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubjectPaper
        fields = ("id", "subject", "paper_number", "weight")


@api_view(["GET", "POST"])
def subject_paper_list(request):
    school_id, error = _scope(request)
    if error:
        return error

    if request.method == "GET":
        papers = SubjectPaper.objects.all()
        if school_id is not None:
            papers = papers.filter(subject__school_id=school_id)
        subject_id = request.query_params.get("subject")
        if subject_id and subject_id.isdigit():
            papers = papers.filter(subject_id=int(subject_id))
        return Response(SubjectPaperSerializer(papers, many=True).data)

    if not request.user.is_superuser and not SchoolAdminProfile.objects.filter(
        user=request.user
    ).exists():
        return Response({"detail": "Admins only."}, status=403)

    serializer = SubjectPaperSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    data = serializer.validated_data
    subject = data["subject"]
    if school_id is not None and subject.school_id != school_id:
        return Response({"detail": "Subject must belong to your school."}, status=403)
    existing = SubjectPaper.objects.filter(subject=subject).aggregate(t=Sum("weight"))["t"]
    if (existing or Decimal("0")) + data["weight"] > 100:
        return Response({"weight": ["Paper weights for a subject cannot exceed 100."]}, status=400)
    serializer.save()
    return Response(serializer.data, status=201)
