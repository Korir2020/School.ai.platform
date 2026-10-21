"""Ranking over an explicit population with an explicit tie policy."""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Sequence


class RankingError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    student_id: str
    value: Optional[Decimal]      # ranking metric (e.g. total or mean)
    complete: bool = True
    status: str = "active"        # active | withdrawn | exempt
    group: str = ""               # class/stream key; used for membership filtering


@dataclass
class RankingResult:
    population: str
    tie_policy: str
    population_size: int
    ranks: dict = field(default_factory=dict)       # student_id -> rank
    excluded: dict = field(default_factory=dict)    # student_id -> reason


def rank(candidates: Sequence[Candidate], *, population: str, tie_policy: str = "competition",
         include_incomplete: bool = False, group: Optional[str] = None) -> RankingResult:
    """Rank the FULL eligible population (never just the printed selection).
    tie_policy: competition (1,2,2,4) | dense (1,2,2,3) | ordinal (1,2,3,4 by student_id)."""
    if tie_policy not in ("competition", "dense", "ordinal"):
        raise RankingError(f"unknown tie policy {tie_policy}")
    if len({c.student_id for c in candidates}) != len(candidates):
        raise RankingError("duplicate student in ranking population")
    res = RankingResult(population, tie_policy, 0)
    eligible = []
    for c in candidates:
        if group is not None and c.group != group:
            res.excluded[c.student_id] = "not in group"
        elif c.status != "active":
            res.excluded[c.student_id] = c.status
        elif c.value is None:
            res.excluded[c.student_id] = "no result"
        elif not c.complete and not include_incomplete:
            res.excluded[c.student_id] = "incomplete results"
        else:
            eligible.append(c)
    eligible.sort(key=lambda c: (-c.value, c.student_id))
    res.population_size = len(eligible)
    prev_val, comp_rank, dense_rank = None, 0, 0
    for i, c in enumerate(eligible, start=1):
        if c.value != prev_val:
            comp_rank, dense_rank, prev_val = i, dense_rank + 1, c.value
        res.ranks[c.student_id] = {"competition": comp_rank, "dense": dense_rank, "ordinal": i}[tie_policy]
    return res
