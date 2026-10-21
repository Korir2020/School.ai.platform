"""Single trusted grading service. All grades, points, totals and means
come from here; frontends and exports must never recompute them."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_DOWN, InvalidOperation
from enum import Enum
from typing import Optional, Sequence

HUNDRED = Decimal("100")
_ROUNDING = {"half_up": ROUND_HALF_UP, "half_even": ROUND_HALF_EVEN, "down": ROUND_DOWN}


class GradingError(ValueError):
    pass


def to_decimal(value, name="value") -> Decimal:
    if isinstance(value, bool) or value is None:
        raise GradingError(f"{name}: invalid number {value!r}")
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise GradingError(f"{name}: invalid number {value!r}")
    if not d.is_finite():
        raise GradingError(f"{name}: must be finite")
    return d


class MarkStatus(str, Enum):
    SCORED = "scored"        # a real mark; zero is a legitimate score
    MISSING = "missing"      # not yet entered -> pending, never zero
    ABSENT = "absent"        # sat-out; policy decides
    EXEMPT = "exempt"        # excluded from totals and max
    WITHDRAWN = "withdrawn"  # excluded from totals and max


@dataclass(frozen=True)
class GradeBand:
    label: str
    min_pct: Decimal      # inclusive
    max_pct: Decimal      # exclusive, except top band (100 inclusive)
    points: Decimal = Decimal(0)


@dataclass(frozen=True)
class GradingScheme:
    bands: tuple
    pass_pct: Decimal = Decimal(40)
    decimals: int = 2
    rounding: str = "half_up"
    # "total_over_max": sum(marks)/sum(max)  (correct for unequal maximums)
    # "average_of_percentages": mean of per-subject percentages
    mean_rule: str = "total_over_max"
    absent_policy: str = "pending"  # "pending" | "zero" | "exclude"
    best_n: Optional[int] = None    # e.g. 7 => KCSE "best 7" points; None => all subjects

    def __post_init__(self):
        validate_bands(self.bands)
        if self.rounding not in _ROUNDING:
            raise GradingError(f"unknown rounding {self.rounding}")
        if self.mean_rule not in ("total_over_max", "average_of_percentages"):
            raise GradingError(f"unknown mean_rule {self.mean_rule}")
        if self.absent_policy not in ("pending", "zero", "exclude"):
            raise GradingError(f"unknown absent_policy {self.absent_policy}")
        if self.decimals < 0:
            raise GradingError("decimals must be >= 0")
        if self.best_n is not None and self.best_n < 1:
            raise GradingError("best_n must be >= 1")

    @property
    def max_points(self) -> Decimal:
        return max(b.points for b in self.bands)

    def label_for_points(self, pts: Decimal) -> Optional[str]:
        """Grade label for a (mean) points value, rounded half-up to a whole point."""
        whole = pts.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        cands = [b for b in self.bands if b.points == whole]
        return max(cands, key=lambda b: b.min_pct).label if cands else None

    def quantize(self, d: Decimal) -> Decimal:
        return d.quantize(Decimal(1).scaleb(-self.decimals), rounding=_ROUNDING[self.rounding])

    def grade_for(self, pct: Decimal) -> GradeBand:
        """Grade a percentage (already rounded by caller where policy says so)."""
        if pct < 0 or pct > HUNDRED:
            raise GradingError(f"percentage out of range: {pct}")
        for b in self.bands:
            if b.min_pct <= pct < b.max_pct or (b.max_pct == HUNDRED and pct == HUNDRED):
                return b
        raise GradingError("no band matched (scheme invalid)")  # unreachable if validated


def make_scheme(bands: Sequence[tuple], **kw) -> GradingScheme:
    """bands: (label, min_pct, max_pct, points) tuples."""
    built = tuple(GradeBand(l, to_decimal(a, "min"), to_decimal(b, "max"), to_decimal(p, "points"))
                  for l, a, b, p in bands)
    if "pass_pct" in kw:
        kw["pass_pct"] = to_decimal(kw["pass_pct"], "pass_pct")
    return GradingScheme(bands=built, **kw)


def validate_bands(bands: Sequence[GradeBand]) -> None:
    if not bands:
        raise GradingError("at least one grade band is required")
    ordered = sorted(bands, key=lambda b: b.min_pct)
    if len({b.label for b in ordered}) != len(ordered):
        raise GradingError("duplicate grade labels")
    if ordered[0].min_pct != 0:
        raise GradingError("lowest band must start at 0 (gap below)")
    if ordered[-1].max_pct != HUNDRED:
        raise GradingError("highest band must end at 100 (gap above)")
    for b in ordered:
        if b.max_pct <= b.min_pct:
            raise GradingError(f"band {b.label}: max must exceed min")
    for prev, nxt in zip(ordered, ordered[1:]):
        if nxt.min_pct < prev.max_pct:
            raise GradingError(f"bands {prev.label} and {nxt.label} overlap")
        if nxt.min_pct > prev.max_pct:
            raise GradingError(f"gap between {prev.label} and {nxt.label}")


@dataclass(frozen=True)
class Component:
    """One assessment (CAT, exam...). weight is relative; final = weighted % * subject max."""
    score: Optional[object]
    max_mark: object
    weight: object = 1
    status: MarkStatus = MarkStatus.SCORED
    name: str = ""                              # e.g. "CAT 1", "End Term"; display only


@dataclass(frozen=True)
class SubjectEntry:
    subject: str
    max_mark: object
    components: tuple = ()
    score: Optional[object] = None              # simple single-mark subjects
    status: MarkStatus = MarkStatus.SCORED
    teacher: str = ""
    remarks: str = ""


@dataclass
class SubjectResult:
    subject: str
    status: str
    score: Optional[Decimal]
    max_mark: Decimal
    pct: Optional[Decimal]
    grade: Optional[str]
    points: Optional[Decimal]
    passed: Optional[bool]
    counted: bool
    teacher: str = ""
    remarks: str = ""


@dataclass
class StudentSummary:
    subjects: list
    total: Decimal
    max_total: Decimal
    mean_pct: Optional[Decimal]
    mean_grade: Optional[str]
    total_points: Decimal
    subjects_completed: int
    pending: int
    excluded: int
    is_complete: bool
    notes: list = field(default_factory=list)
    best_points: Decimal = Decimal(0)        # sum of best-N subject points
    max_points: Decimal = Decimal(0)         # N * highest grade points
    mean_points: Optional[Decimal] = None    # best_points / N
    mean_points_grade: Optional[str] = None


def _component_score(entry: SubjectEntry, scheme: GradingScheme):
    """Return (status, score or None) for the subject on its own max_mark scale."""
    smax = to_decimal(entry.max_mark, "max_mark")
    if smax <= 0:
        raise GradingError(f"{entry.subject}: max_mark must be positive")
    if not entry.components:
        if entry.status != MarkStatus.SCORED or entry.score is None:
            return (entry.status if entry.status != MarkStatus.SCORED else MarkStatus.MISSING), None, smax
        s = to_decimal(entry.score, f"{entry.subject} score")
        if s < 0 or s > smax:
            raise GradingError(f"{entry.subject}: score {s} outside 0..{smax}")
        return MarkStatus.SCORED, s, smax
    wsum = Decimal(0)
    acc = Decimal(0)
    for c in entry.components:
        w = to_decimal(c.weight, "weight")
        cm = to_decimal(c.max_mark, "component max")
        if w <= 0 or cm <= 0:
            raise GradingError(f"{entry.subject}: weight and max must be positive")
        if c.status != MarkStatus.SCORED or c.score is None:
            st = c.status if c.status != MarkStatus.SCORED else MarkStatus.MISSING
            return st, None, smax  # any non-scored component keeps the subject non-final
        cs = to_decimal(c.score, "component score")
        if cs < 0 or cs > cm:
            raise GradingError(f"{entry.subject}: component score {cs} outside 0..{cm}")
        acc += (cs / cm) * w
        wsum += w
    return MarkStatus.SCORED, (acc / wsum) * smax, smax


def evaluate_student(entries: Sequence[SubjectEntry], scheme: GradingScheme) -> StudentSummary:
    results, total, max_total, points = [], Decimal(0), Decimal(0), Decimal(0)
    pcts, completed, pending, excluded = [], 0, 0, 0
    notes = []
    for e in entries:
        status, score, smax = _component_score(e, scheme)
        if status in (MarkStatus.EXEMPT, MarkStatus.WITHDRAWN) or (
                status == MarkStatus.ABSENT and scheme.absent_policy == "exclude"):
            excluded += 1
            results.append(SubjectResult(e.subject, status.value, None, smax, None, None, None, None,
                                         False, e.teacher, e.remarks))
            continue
        if status == MarkStatus.ABSENT and scheme.absent_policy == "zero":
            status, score = MarkStatus.SCORED, Decimal(0)
        if status != MarkStatus.SCORED:
            pending += 1
            results.append(SubjectResult(e.subject, status.value, None, smax, None, None, None, None,
                                         False, e.teacher, e.remarks))
            continue
        score_q = scheme.quantize(score)
        pct = scheme.quantize(score / smax * HUNDRED)
        band = scheme.grade_for(min(pct, HUNDRED))
        results.append(SubjectResult(e.subject, "scored", score_q, smax, pct, band.label, band.points,
                                     pct >= scheme.pass_pct, True, e.teacher, e.remarks))
        total += score_q
        max_total += smax
        points += band.points
        pcts.append(pct)
        completed += 1
    mean_pct = mean_grade = None
    if completed:
        raw = (total / max_total * HUNDRED) if scheme.mean_rule == "total_over_max" \
            else sum(pcts) / len(pcts)
        mean_pct = scheme.quantize(raw)
        mean_grade = scheme.grade_for(min(mean_pct, HUNDRED)).label
    if pending:
        notes.append(f"{pending} result(s) pending; totals cover completed subjects only")
    pts_sorted = sorted((r.points for r in results if r.counted), reverse=True)
    used = pts_sorted[:scheme.best_n] if scheme.best_n else pts_sorted
    best_points = sum(used, Decimal(0))
    mean_points = scheme.quantize(best_points / len(used)) if used else None
    if scheme.best_n and 0 < completed < scheme.best_n:
        notes.append(f"only {completed} of required {scheme.best_n} subjects completed")
    n_for_max = scheme.best_n or len(used)
    return StudentSummary(results, total, max_total, mean_pct, mean_grade, points,
                          completed, pending, excluded, pending == 0 and completed > 0, notes,
                          best_points=best_points, max_points=scheme.max_points * n_for_max,
                          mean_points=mean_points,
                          mean_points_grade=scheme.label_for_points(mean_points) if mean_points is not None else None)
