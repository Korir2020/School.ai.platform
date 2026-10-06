from django.db.models import Avg, Count


def unofficial(rows):
    counts = {"draft": 0, "submitted": 0}
    for r in rows.values("status").annotate(n=Count("id")):
        counts[r["status"]] = r["n"]
    subjects = rows.values("subject__name").annotate(
        average=Avg("marks"), entries=Count("id")).order_by("subject__name")
    return {
        "note": "Draft and submitted marks. Not official.",
        **counts,
        "subjects": [
            {"subject": r["subject__name"], "entries": r["entries"],
             "average": round(float(r["average"]), 2)}
            for r in subjects
        ],
    }
