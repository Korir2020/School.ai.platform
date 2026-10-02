from decimal import Decimal

SHARP_DROP = Decimal("10")  # fall in one exam that raises a flag
TREND_BAND = Decimal("3")   # net change needed to call a trend


def analyse(points):
    """points: [(label, average Decimal, {subject: Decimal})], oldest first."""
    out = {"exams": len(points), "change": None, "trend": "not_enough_data",
           "flags": [], "biggest_subject_drops": []}
    if len(points) < 2:
        return out
    avgs = [p[1] for p in points]
    steps = [b - a for a, b in zip(avgs, avgs[1:])]
    out["change"] = str(steps[-1])
    net = avgs[-1] - avgs[max(0, len(avgs) - 3)]
    out["trend"] = ("improving" if net >= TREND_BAND
                    else "declining" if net <= -TREND_BAND else "steady")
    if steps[-1] <= -SHARP_DROP:
        out["flags"].append({"flag": "sharp_drop", "reason":
            f"Average fell {-steps[-1]} points since the previous exam."})
    if len(steps) >= 2 and steps[-1] < 0 and steps[-2] < 0:
        out["flags"].append({"flag": "decline_streak", "reason":
            "Average fell in each of the last two exams."})
    before, now = points[-2][2], points[-1][2]
    drops = sorted((now[s] - before[s], s) for s in now if s in before)
    out["biggest_subject_drops"] = [
        {"subject": s, "change": str(d)} for d, s in drops[:3] if d < 0]
    return out
