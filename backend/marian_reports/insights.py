"""Insight engine (Part 2): simple statistics only. No ML, no predictions.

Pure functions. They never read a database and never invent data.
Input is a per-subject series of REAL percentages from finalized exams.
Callers must leave out missing / absent / exempt / withdrawn marks
(a missing mark is never treated as 0). Every output is labelled
"calculated" so readers can tell it from a teacher's judgement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

LABEL = "calculated"
METHOD = ("Calculated from this student's own published exam percentages "
          "using a straight-line fit. A statistical summary, not a prediction.")

D = Decimal


@dataclass(frozen=True)
class InsightConfig:
    drop_threshold: Decimal = D("15")   # percentage points fall that is flagged
    trend_threshold: Decimal = D("2")   # slope (points per exam) to call rising/falling
    min_points_trend: int = 3           # fewer points -> no trend line


@dataclass(frozen=True)
class Point:
    exam_id: str
    label: str                 # e.g. "END T2'26"
    sequence: int              # chronological order
    pct: Optional[Decimal]     # None = no real mark; point is ignored


@dataclass(frozen=True)
class SubjectInsight:
    subject: str
    n_points: int
    latest: Optional[Decimal]
    previous: Optional[Decimal]
    change: Optional[Decimal]          # latest - previous, percentage points
    slope: Optional[Decimal]           # points per exam, None if too little data
    trend: str                         # rising | falling | steady | insufficient
    drop_flag: bool
    drop_size: Optional[Decimal]       # positive number of points lost
    drop_from: str = ""                # label of the exam compared against
    label: str = LABEL
    method: str = METHOD


def _clean(points: Sequence[Point]) -> List[Point]:
    """Keep only real marks, in chronological order. Never turns None into 0."""
    real = [p for p in points if p.pct is not None]
    return sorted(real, key=lambda p: p.sequence)


def slope(points: Sequence[Point]) -> Optional[Decimal]:
    """Least-squares slope of pct against position (0,1,2...). Needs >= 2 points."""
    pts = _clean(points)
    n = len(pts)
    if n < 2:
        return None
    xs = [D(i) for i in range(n)]
    ys = [p.pct for p in pts]
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return num / den


def analyse_subject(subject: str, points: Sequence[Point],
                    cfg: InsightConfig = InsightConfig()) -> SubjectInsight:
    pts = _clean(points)
    n = len(pts)
    if n == 0:
        return SubjectInsight(subject, 0, None, None, None, None,
                              "insufficient", False, None)
    latest = pts[-1].pct
    if n == 1:
        return SubjectInsight(subject, 1, latest, None, None, None,
                              "insufficient", False, None)
    prev = pts[-2]
    change = latest - prev.pct
    s = slope(pts) if n >= cfg.min_points_trend else None
    if s is None:
        trend = "insufficient"
    elif s >= cfg.trend_threshold:
        trend = "rising"
    elif s <= -cfg.trend_threshold:
        trend = "falling"
    else:
        trend = "steady"
    drop = (-change) >= cfg.drop_threshold
    return SubjectInsight(
        subject, n, latest, prev.pct, change, s, trend, drop,
        (-change) if drop else None, prev.label if drop else "")


def analyse_student(series: Dict[str, Sequence[Point]],
                    cfg: InsightConfig = InsightConfig()) -> List[SubjectInsight]:
    """series: subject -> points. Result is sorted by subject name."""
    return [analyse_subject(sub, series[sub], cfg) for sub in sorted(series)]


def _f(d: Decimal) -> str:
    return f"{d:.1f}"


def facts(insights: Sequence[SubjectInsight]) -> List[str]:
    """Plain-language lines, each labelled 'calculated'. Only states what the numbers show."""
    out: List[str] = []
    for i in insights:
        if i.drop_flag:
            out.append(f"{i.subject}: fell {_f(i.drop_size)} points since "
                       f"{i.drop_from} ({_f(i.previous)}% to {_f(i.latest)}%) [{LABEL}]")
        if i.trend in ("rising", "falling"):
            out.append(f"{i.subject}: {i.trend} trend of {_f(abs(i.slope))} points "
                       f"per exam over {i.n_points} exams [{LABEL}]")
    return out


def ranked_facts(insights, limit=None):
    """Like facts(), but biggest drops first, then steepest falls, then rises.
    limit caps the number of lines (the report's insight box is small)."""
    items = []
    for ins in insights:
        for line in facts([ins]):
            if "fell" in line.split(":", 1)[1][:6]:
                items.append((0, -ins.drop_size, ins.subject, line))
            elif ins.trend == "falling":
                items.append((1, ins.slope, ins.subject, line))
            else:
                items.append((2, -(ins.slope or 0), ins.subject, line))
    items.sort(key=lambda x: (x[0], x[1], x[2]))
    out = [x[3] for x in items]
    return out if limit is None else out[:max(limit, 0)]
