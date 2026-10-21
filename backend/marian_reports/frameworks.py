"""Assessment frameworks. Each maps a framework key to a grading scheme.
Existing 8-4-4 (KCSE-style) scheme is unchanged; this only ADDS entries.
Every result is an internal school calculation, never an official KNEC result."""
from dataclasses import dataclass
from typing import Callable

from .grading import GradingScheme, make_scheme
from .schemes import kcse_scheme

INTERNAL_NOTE = "Internal school result - not an official KNEC result."

# (label, min_pct inclusive, max_pct exclusive, points). Reported KJSEA levels;
# see docs/RULES.md for status. 10% and below = BE2, 11-20 = BE1, ... 90-100 = EE1.
KJSEA_BANDS = [
    ("BE2", 0, 11, 1), ("BE1", 11, 21, 2), ("AE2", 21, 31, 3), ("AE1", 31, 41, 4),
    ("ME2", 41, 58, 5), ("ME1", 58, 75, 6), ("EE2", 75, 90, 7), ("EE1", 90, 100, 8),
]


def kjsea_scheme(**overrides) -> GradingScheme:
    kw = dict(pass_pct=0, decimals=2, rounding="half_up", mean_rule="total_over_max",
              absent_policy="pending", best_n=None)
    kw.update(overrides)
    return make_scheme(KJSEA_BANDS, **kw)


@dataclass(frozen=True)
class Framework:
    key: str
    name: str
    stage: str
    scheme_factory: Callable[[], GradingScheme]
    note: str = INTERNAL_NOTE

    def scheme(self) -> GradingScheme:
        return self.scheme_factory()


FRAMEWORKS = {
    "kcse_844": Framework("kcse_844", "8-4-4 secondary (12-point scale, best 7)",
                          "secondary_844", kcse_scheme),
    "cbe_junior_levels": Framework("cbe_junior_levels",
                                   "Junior school achievement levels (EE1-BE2, 8 points)",
                                   "junior", kjsea_scheme),
}


def get_framework(key: str) -> Framework:
    if key not in FRAMEWORKS:
        raise KeyError(f"unknown framework {key}")
    return FRAMEWORKS[key]


# Stage presets: named bundles of report settings. Wording/visibility only; no grading rules here.
STAGE_PRESETS = {
    "kcse_844": {"sections": {}, "labels": {}},
    "cbe_junior_levels": {
        "sections": {"positions": False, "subject_position": False,
                     "gender_position": False, "kcpe": False,
                     "aggregate": False, "performance_chart": False, "history": False},
        "labels": {"subject": "LEARNING AREA"},
    },
}


def config_for(key, **overrides):
    from .config import ReportConfig
    get_framework(key)
    preset = STAGE_PRESETS.get(key, {})
    cfg = ReportConfig(**overrides)
    cfg.sections.update(preset.get("sections", {}))
    cfg.labels.update(preset.get("labels", {}))
    return cfg


def service_for(ds, key):
    from .assembler import ReportService
    return ReportService(ds, get_framework(key).scheme(), config_for(key))
