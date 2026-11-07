from django.db.models import Avg, Count, Max, Min, Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from schools.models import Performance, SchoolAdminProfile

SPREAD = 40


def _flags(g):
    out = []
    if g["avg"] is None:
        return out
    if g["hundreds"]:
        out.append("has_hundred")
    if g["high"] - g["avg"] >= SPREAD or g["avg"] - g["low"] >= SPREAD:
        out.append("wide_spread")
    return out


@api_view(["GET"])
def approvals_summary(request):
    boss = SchoolAdminProfile.objects.filter(user=request.user).first()
    if boss is None:
        return Response({"detail": "Admins only."}, status=403)
    rows = Performance.objects.filter(
        student__school_id=boss.school_id, status="submitted")
    groups = rows.values(
        "subject_id", "subject__name", "term_id", "term__name",
        "assessment_type", "paper_number",
    ).annotate(
        count=Count("id"),
        scored=Count("id", filter=Q(mark_status="scored")),
        absent=Count("id", filter=Q(mark_status="absent")),
        exempted=Count("id", filter=Q(mark_status="exempted")),
        not_assessed=Count("id", filter=Q(mark_status="not_assessed")),
        pending=Count("id", filter=Q(mark_status="pending")),
        avg=Avg("marks", filter=Q(mark_status="scored")),
        low=Min("marks", filter=Q(mark_status="scored")),
        high=Max("marks", filter=Q(mark_status="scored")),
        hundreds=Count("id", filter=Q(mark_status="scored", marks=100)),
    ).order_by("subject__name", "term_id", "assessment_type", "paper_number")
    results = []
    for g in groups:
        f = {**g, "avg": float(g["avg"]) if g["avg"] is not None else None,
             "low": float(g["low"]) if g["low"] is not None else None,
             "high": float(g["high"]) if g["high"] is not None else None}
        results.append({
            "subject_id": g["subject_id"], "subject": g["subject__name"],
            "term_id": g["term_id"], "term": g["term__name"],
            "assessment_type": g["assessment_type"], "paper_number": g["paper_number"],
            "count": g["count"], "scored": g["scored"],
            "absent": g["absent"], "exempted": g["exempted"],
            "not_assessed": g["not_assessed"], "pending": g["pending"],
            "average": round(f["avg"], 2) if f["avg"] is not None else None,
            "lowest": f["low"], "highest": f["high"], "flags": _flags(f),
        })
    return Response({
        "total_submitted": rows.count(),
        "flagged_groups": sum(1 for r in results if r["flags"]),
        "results": results,
    })
