from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ReportConfig:
    # --- policy
    require_published: bool = True
    allow_provisional: bool = False
    rank_by: str = "best_points"          # best_points | total_marks
    tie_policy: str = "competition"       # competition | dense | ordinal
    include_incomplete_in_rank: bool = False
    subject_rank_scope: str = "stream"    # stream | overall
    rank_note: str = "Position ranked by KCSE Best 7"
    weak_pct: float = 50.0                # subjects below this are "needing improvement"
    strong_count: int = 2
    history_limit: int = 6
    trend_max_facts: int = 2   # max 'calculated' lines in the small insight box
    max_batch: int = 500
    # --- sections (administrators toggle these)
    sections: dict = field(default_factory=lambda: {
        "gender": True, "kcpe": True, "gender_position": True, "performance_chart": True,
        "insight": True, "history": True, "class_teacher_remark": True, "principal_remark": True,
        "school_dates": True, "fees": False, "grading_key": True, "signatures": True,
        "stamp": True, "qr": True, "attendance": False, "assessment_breakdown": False,
    })
    remark_bands: list = field(default_factory=lambda: [
        (75, "Excellent"), (60, "Good"), (50, "Fair"), (0, "Keep Trying")])
    footer_note: str = "Kindly clear any school fees balance before or on the opening date."
    paper: str = "A4"
    labels: dict = field(default_factory=lambda: {"subject": "SUBJECT"})  # column wording

    def remark_for_pct(self, pct) -> str:
        for floor, text in self.remark_bands:
            if pct >= floor:
                return text
        return ""
