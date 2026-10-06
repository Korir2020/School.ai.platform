from django.db.models import Avg, Count, Max, Min
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Performance, SchoolAdminProfile, Term
from .permissions import get_user_school_id
from .unofficial import unofficial


@api_view(["GET"])
def term_summary(request, term_id):
    terms = Term.objects.select_related("academic_year")
    if not request.user.is_superuser:
        if not SchoolAdminProfile.objects.filter(user=request.user).exists():
            return Response({"detail": "Admins only."}, status=403)
        terms = terms.filter(academic_year__school_id=get_user_school_id(request.user))
    term = terms.filter(pk=term_id).first()
    if term is None:
        return Response({"detail": "Not found."}, status=404)

    marks = Performance.objects.filter(term=term)
    final = marks.filter(status__in=["approved", "locked"])
    rows = (
        final.values("subject__name")
        .annotate(average=Avg("marks"), highest=Max("marks"),
                  lowest=Min("marks"), entries=Count("id"))
        .order_by("subject__name")
    )
    return Response({
        "term": term.name,
        "academic_year": term.academic_year.name,
        "subjects": [
            {
                "subject": r["subject__name"],
                "average": round(float(r["average"]), 2),
                "highest": str(r["highest"]),
                "lowest": str(r["lowest"]),
                "entries": r["entries"],
            }
            for r in rows
        ],
        "pending_marks": marks.count() - final.count(),
        "unofficial": unofficial(
            marks.exclude(status__in=["approved", "locked"])),
    })
