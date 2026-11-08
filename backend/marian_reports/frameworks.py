"""Assessment frameworks. Each maps a framework key to a grading scheme.
Existing 8-4-4 (KCSE-style) scheme is unchanged; this only ADDS entries.
Every result is an internal school calculation, never an official KNEC result."""
from dataclasses import dataclass
from typing import Callable

from .grading import GradingError, GradingScheme, make_scheme
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


def primary_school_scheme() -> GradingScheme:
    """CBC Primary has no built-in national percentage bands in Marian.

    Report APIs must supply the school's saved or exam-frozen grading scheme;
    this callable intentionally prevents a framework preset being mistaken for
    an official Primary grading rule.
    """
    raise GradingError("CBC Primary requires a school-configured grading scale.")


def junior_school_scheme() -> GradingScheme:
    """CBC Junior has no built-in national percentage bands in Marian.

    Reports must use the school's saved or exam-frozen scheme. Achievement
    descriptors are separately authored by the school in its level scale.
    """
    raise GradingError("CBC Junior requires a school-configured grading scale.")


def senior_school_scheme() -> GradingScheme:
    """CBC Senior grading is configured by each school; no national bands are seeded."""
    raise GradingError("CBC Senior requires a school-configured grading scale.")


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
    "cbe_primary": Framework("cbe_primary", "CBC Primary (Grades 1–6; school-configured)",
                             "primary", primary_school_scheme),
    "kcse_844": Framework("kcse_844", "8-4-4 secondary (12-point scale, best 7)",
                          "secondary_844", kcse_scheme),
    "cbe_junior_levels": Framework("cbe_junior_levels",
                                   'Junior school achievement levels (EE1-BE2, 8 points)',
                                   "junior", kjsea_scheme),
    "cbe_senior": Framework("cbe_senior",
                             "CBC Senior (Grades 10–12; school-configured)",
                             "senior", senior_school_scheme),
}

CBC_LEVEL_FRAMEWORKS = frozenset(("cbe_primary", "cbe_junior_levels"))
CBC_REPORT_FRAMEWORKS = CBC_LEVEL_FRAMEWORKS | frozenset(("cbe_senior",))


def get_framework(key: str) -> Framework:
    if key not in FRAMEWORKS:
        raise KeyError(f"unknown framework {key}")
    return FRAMEWORKS[key]


# Stage presets: named bundles of report settings. Wording/visibility only; no grading rules here.
STAGE_PRESETS = {
    "cbe_primary": {
        # School ranking policy is opt-in for Primary; schools can switch these
        # report sections on after reviewing their own policy.
        "sections": {"positions": False, "subject_position": False,
                     "gender_position": False, "kcpe": False},
        "labels": {"subject": "LEARNING AREA"},
    },
    "kcse_844": {"sections": {}, "labels": {}},
    "cbe_junior_levels": {
        "sections": {"positions": False, "subject_position": False,
                     "gender_position": False, "kcpe": False,
                     "aggregate": False, "performance_chart": False, "history": False},
        "labels": {"subject": "LEARNING AREA"},
    },
    "cbe_senior": {
        # Senior rankings are opt-in; if enabled, the report service compares
        # learners only within the same pathway and exact registered-subject set.
        "sections": {"positions": False, "subject_position": False,
                     "gender_position": False, "kcpe": False},
        "labels": {"subject": "SUBJECT"},
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
