from decimal import Decimal

from django.db.models import Sum
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import SchoolAdminProfile, SubjectPaper
from .papers import LOCKED_MSG, SubjectPaperSerializer, weights_locked
from .views import _scope


@api_view(["GET", "PATCH", "DELETE"])
def subject_paper_detail(request, pk):
    school_id, error = _scope(request)
    if error:
        return error
    if request.method != "GET" and not (
        request.user.is_superuser
        or SchoolAdminProfile.objects.filter(user=request.user).exists()
    ):
        return Response({"detail": "Admins only."}, status=403)

    papers = SubjectPaper.objects.select_related("subject")
    if school_id is not None:
        papers = papers.filter(subject__school_id=school_id)
    paper = papers.filter(pk=pk).first()
    if paper is None:
        return Response({"detail": "Not found."}, status=404)

    if request.method == "GET":
        return Response(SubjectPaperSerializer(paper).data)

    if request.method == "DELETE":
        if weights_locked(paper.subject):
            return Response(LOCKED_MSG, status=409)
        paper.delete()
        return Response(status=204)

    data = {k: request.data[k] for k in ("weight", "max_marks") if k in request.data}
    if not data:
        return Response({"detail": "Only weight and max_marks can be edited."}, status=400)
    serializer = SubjectPaperSerializer(paper, data=data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    if weights_locked(paper.subject):
        return Response(LOCKED_MSG, status=409)
    new_weight = serializer.validated_data.get("weight", paper.weight)
    others = (
        SubjectPaper.objects.filter(subject=paper.subject).exclude(pk=paper.pk)
        .aggregate(t=Sum("weight"))["t"]
    ) or Decimal("0")
    if others + new_weight > 100:
        return Response({"weight": ["Paper weights for a subject cannot exceed 100."]}, status=400)
    new_max = serializer.validated_data.get("max_marks")
    if new_max is not None:
        from django.db.models import Max
        from schools.models import Performance
        top = Performance.objects.filter(
            subject=paper.subject, paper_number=paper.paper_number
        ).aggregate(m=Max("marks"))["m"]
        if top is not None and new_max < top:
            return Response({"max_marks": [
                "Marks up to " + format(top.normalize(), "f") + " already exist for this paper."
            ]}, status=400)
    serializer.save()
    return Response(serializer.data)
