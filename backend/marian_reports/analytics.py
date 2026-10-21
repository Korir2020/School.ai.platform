"""Class / stream / subject analytics from the SAME snapshot used for report cards.
Every result carries the population and filters used. Means are weighted by marks
(sum marks / sum max), never an average of percentages."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from .assembler import ReportNotReady, Snapshot, evaluate_student

Q = Decimal("0.01")


def _q(x): return None if x is None else Decimal(x).quantize(Q, rounding=ROUND_HALF_UP)


def _dist(labels, grades):
    return {g: grades.count(g) for g in labels}


def subject_stats(snap: Snapshot, scheme, subject: str, stream=None) -> dict:
    rows, pending = [], 0
    for sid, st in snap.students.items():
        if st.status != "active" or (stream and st.stream != stream): continue
        r = next((x for x in snap.summaries[sid].subjects if x.subject == subject), None)
        if r is None or r.status in ("exempt", "withdrawn"): continue
        if r.counted: rows.append(r)
        else: pending += 1
    labels = [b.label for b in sorted(scheme.bands, key=lambda b: -b.min_pct)]
    out = {"population": f"{snap.class_name}{' ' + stream if stream else ''} · {subject} · {snap.exam.name}",
           "assessed": len(rows), "pending": pending}
    if rows:
        tot, mx = sum(r.score for r in rows), sum(r.max_mark for r in rows)
        scores = [r.score for r in rows]
        out.update(mean_weighted_pct=_q(tot / mx * 100),
                   mean_of_percentages=_q(sum(r.pct for r in rows) / len(rows)),
                   highest=max(scores), lowest=min(scores), median=_q(Decimal(str(median(scores)))),
                   pass_rate=_q(Decimal(sum(1 for r in rows if r.passed)) / len(rows) * 100),
                   grade_distribution=_dist(labels, [r.grade for r in rows]))
    return out


def group_stats(snap: Snapshot, scheme, stream=None) -> dict:
    ids = [i for i, s in snap.students.items() if (not stream or s.stream == stream) and s.status == "active"]
    done = [snap.summaries[i] for i in ids if snap.summaries[i].subjects_completed]
    incomplete = [i for i in ids if not snap.summaries[i].is_complete]
    labels = [b.label for b in sorted(scheme.bands, key=lambda b: -b.min_pct)]
    out = {"population": f"{snap.class_name}{' ' + stream if stream else ' (all streams)'} · {snap.exam.name}",
           "eligible": len(ids), "assessed": len(done), "incomplete": len(incomplete),
           "withdrawn_excluded": sum(1 for s in snap.students.values() if s.status != "active" and (not stream or s.stream == stream))}
    if done:
        mp = [d.mean_points for d in done]
        tot, mx = sum(d.total for d in done), sum(d.max_total for d in done)
        out.update(mean_points=_q(sum(mp) / len(mp)), mean_grade=scheme.label_for_points(sum(mp) / len(mp)),
                   mean_weighted_pct=_q(tot / mx * 100),
                   grade_distribution=_dist(labels, [d.mean_points_grade for d in done]))
        subs = sorted({r.subject for d in done for r in d.subjects})
        out["subjects"] = [{"subject": s, **{k: v for k, v in subject_stats(snap, scheme, s, stream).items()
                                              if k in ("assessed", "pending", "mean_weighted_pct", "highest", "lowest", "pass_rate")}}
                           for s in subs]
    return out


def support_list(snap: Snapshot, threshold_points=4) -> list:
    """Students needing academic support: calculated, for staff review (not an automatic decision)."""
    out = []
    for sid, sm in snap.summaries.items():
        st = snap.students[sid]
        if st.status == "active" and sm.mean_points is not None and sm.mean_points < threshold_points:
            out.append({"student_id": sid, "adm_no": st.adm_no, "stream": st.stream, "mean_points": sm.mean_points})
    return sorted(out, key=lambda r: r["mean_points"])


def ranking_table(snap: Snapshot, scope="overall", stream=None) -> dict:
    res = snap.overall if scope == "overall" else snap.stream[stream]
    rows = []
    for sid, pos in sorted(res.ranks.items(), key=lambda kv: (kv[1], snap.students[kv[0]].adm_no)):
        st, sm = snap.students[sid], snap.summaries[sid]
        rows.append({"position": pos, "student_id": sid, "adm_no": st.adm_no, "name": st.full_name, "stream": st.stream,
                     "total": sm.total, "best_points": sm.best_points, "mean_points": sm.mean_points,
                     "mean_grade": sm.mean_points_grade})
    return {"population": res.population, "tie_policy": res.tie_policy, "included": res.population_size,
            "excluded": dict(res.excluded), "rows": rows}


# ---- school-wide analytics (published results only) ----

def _need_published(snap):
    if not snap.exam.published:
        raise ReportNotReady("unpublished", "Analytics use finalized (published) results only.")


def _active(snap, stream=None):
    return [i for i, s in snap.students.items()
            if s.status == "active" and (not stream or s.stream == stream)]


def _usable(snap, sid):
    return [r for r in snap.summaries[sid].subjects
            if r.counted and r.status not in ("exempt", "withdrawn")
            and r.score is not None and r.grade is not None]


def _group_row(snap, scheme, label, ids, include_aggregate):
    labels = [b.label for b in sorted(scheme.bands, key=lambda b: -b.min_pct)]
    per = {i: _usable(snap, i) for i in ids}
    res = [r for v in per.values() for r in v]
    out = {"stream": label, "eligible": len(ids),
           "assessed": sum(1 for v in per.values() if v), "subject_results": len(res)}
    if res:
        tot, mx = sum(r.score for r in res), sum(r.max_mark for r in res)
        out["mean_weighted_pct"] = _q(tot / mx * 100) if mx else None
        out["level_distribution"] = _dist(labels, [r.grade for r in res])
    if include_aggregate:
        mps = [snap.summaries[i].mean_points for i in ids
               if snap.summaries[i].mean_points is not None]
        out["mean_points"] = _q(sum(mps) / len(mps)) if mps else None
    return out


def stream_comparison(snap: Snapshot, scheme, include_aggregate=True) -> dict:
    """Per-stream and overall comparison. Calculated from published results only."""
    _need_published(snap)
    ids = _active(snap)
    streams = sorted({snap.students[i].stream for i in ids})
    return {"population": f"{snap.class_name} \u00b7 {snap.exam.name}",
            "basis": "calculated from published results; internal, not official",
            "streams": [_group_row(snap, scheme, s, _active(snap, s), include_aggregate)
                        for s in streams],
            "overall": _group_row(snap, scheme, "All streams", ids, include_aggregate)}


def _scored_pcts(lines):
    return {r.subject: r.pct for r in lines if r.status == "scored" and r.pct is not None}


def top_improvers(ds, scheme, snap: Snapshot, limit=10, stream=None, min_common=3) -> dict:
    """Biggest average % gain vs the previous published exam, over subjects scored in both."""
    _need_published(snap)
    out = {"population": f"{snap.class_name}{' ' + stream if stream else ''} \u00b7 {snap.exam.name}",
           "method": "mean change in subject % over subjects scored in both exams (calculated)",
           "to_exam": snap.exam.name, "from_exam": None, "compared": 0, "rows": []}
    prior = [e for e in ds.list_exams(snap.school_id)
             if e.sequence < snap.exam.sequence and e.published]
    if not prior:
        out["note"] = "No earlier published exam to compare."
        return out
    prev = max(prior, key=lambda e: e.sequence)
    out["from_exam"] = prev.name
    rows = []
    for sid in _active(snap, stream):
        now = _scored_pcts(snap.summaries[sid].subjects)
        ents = ds.get_entries(snap.school_id, prev.id, sid)
        before = _scored_pcts(evaluate_student(ents, scheme).subjects) if ents else {}
        common = sorted(set(now) & set(before))
        if len(common) < min_common:
            continue
        out["compared"] += 1
        change = sum(now[s] - before[s] for s in common) / len(common)
        if change > 0:
            st = snap.students[sid]
            rows.append({"student_id": sid, "adm_no": st.adm_no, "name": st.full_name,
                         "stream": st.stream, "change_pct": _q(change),
                         "subjects_compared": len(common)})
    rows.sort(key=lambda r: (-r["change_pct"], r["adm_no"]))
    out["rows"] = rows[:limit]
    return out
