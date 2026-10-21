"""Default scheme: Kenyan secondary 12-point scale, best-7 points.
Verified against a real printed report (8 subjects, 262/800, 22/84 points, mean 3.14 D).
Every number is configurable; nothing else in the codebase hardcodes grades."""
from .grading import make_scheme

KCSE_BANDS = [
    ("E", 0, 30, 1), ("D-", 30, 35, 2), ("D", 35, 40, 3), ("D+", 40, 45, 4),
    ("C-", 45, 50, 5), ("C", 50, 55, 6), ("C+", 55, 60, 7), ("B-", 60, 65, 8),
    ("B", 65, 70, 9), ("B+", 70, 75, 10), ("A-", 75, 80, 11), ("A", 80, 100, 12),
]


def kcse_scheme(**overrides):
    kw = dict(pass_pct=40, decimals=2, rounding="half_up", mean_rule="total_over_max",
              absent_policy="pending", best_n=7)
    kw.update(overrides)
    return make_scheme(KCSE_BANDS, **kw)
