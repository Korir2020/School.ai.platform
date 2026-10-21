"""Analysis snapshot + report assembly. The ONLY place report values are computed;
renderers (PDF, HTML, CSV) just display ReportData."""
from __future__ import annotations
import hashlib, hmac, os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from .domain import *
from .config import ReportConfig
from .grading import GradingScheme, evaluate_student, StudentSummary, MarkStatus, to_decimal
from .ranking import Candidate, rank


def _secret() -> bytes:
    return os.environ.get("MARIAN_REPORT_SECRET", "dev-only-change-me").encode()


def sign(report_no: str, snapshot_id: str) -> str:
    return hmac.new(_secret(), f"{report_no}|{snapshot_id}".encode(), hashlib.sha256).hexdigest()[:12]


@dataclass
class Snapshot:
    """Consistent view of one exam for one class level, used for ALL rankings in a run."""
    school_id: str
    exam: Exam
    class_name: str
    students: dict            # id -> Student (full eligible population, incl. withdrawn)
    summaries: dict           # id -> StudentSummary
    overall: object           # RankingResult
    stream: dict              # stream -> RankingResult
    gender: dict              # (stream, gender) -> RankingResult
    subject: dict             # (scope_key, subject) -> RankingResult
    snapshot_id: str
    warnings: list = field(default_factory=list)


@dataclass
class SubjectLine:
    subject: str; status: str; score: Optional[Decimal]; max_mark: Decimal
    pct: Optional[Decimal]; grade: str; points: Optional[Decimal]
    position: str; remark: str; teacher: str


@dataclass
class ReportData:
    report_no: str; school: School; student: Student; exam: Exam
    generated_on: str; subjects: list
    total: Decimal; max_total: Decimal; mean_points: Optional[Decimal]; mean_grade: str
    mean_pct: Optional[Decimal]; best_points: Decimal; max_points: Decimal
    completed: int; pending: int; excluded: int
    positions: dict          # name -> {"pos": int|None, "of": int, "label": str}
    provisional: bool; warnings: list
    history: list            # [{"exam": "END T2'26", "mean": Decimal|None, "grade": str}]
    insight: dict            # {"facts": [...], "recommendation": str, "source": "rules"}
    remarks: dict; dates: dict; fee_note: Optional[str]
    snapshot_id: str; token: str; sections: dict; rank_note: str; grading_key: list
    footer_note: str
    attendance: Optional[dict] = None      # {"open","present","absent","late","pct"} or None
    breakdown: list = field(default_factory=list)          # [{"subject", "parts": [{"name","score","max","pct","status"}]}]
    breakdown_summary: list = field(default_factory=list)
    scale: dict = field(default_factory=dict)  # {'max': float, 'ticks': [(points, label)]}  # [{"name","avg_pct","n","of"}]
    labels: dict = field(default_factory=dict)


def _attendance_view(att, warnings: list):
    """Validated attendance for display. Inconsistent data is left off with a warning, never 'fixed'."""
    if att is None:
        return None
    vals = (att.days_open, att.days_present, att.days_absent, att.days_late)
    if all(v == 0 for v in vals if isinstance(v, int)) and all(isinstance(v, int) for v in vals):
        return None                                           # nothing recorded
    bad = (any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in vals)
           or att.days_open == 0 or att.days_present + att.days_absent > att.days_open
           or att.days_late > att.days_present)
    if bad:
        warnings.append("Attendance record is inconsistent and was left off this report.")
        return None
    pct = (Decimal(att.days_present) * 100 / Decimal(att.days_open)).quantize(Decimal("0.1"), ROUND_HALF_UP)
    return {"open": att.days_open, "present": att.days_present, "absent": att.days_absent,
            "late": att.days_late, "pct": pct}


def _breakdown(entries):
    """Per-subject assessment parts, plus the student's average % per part name across subjects.
    A part that is not scored is shown as pending/absent and never counted as 0."""
    rows, acc = [], {}
    for e in entries:
        if not e.components:
            continue
        parts = []
        for i, c in enumerate(e.components):
            name = (c.name or "").strip() or f"Part {i + 1}"
            ok = c.status == MarkStatus.SCORED and c.score is not None
            pct = (to_decimal(c.score, "score") * 100 / to_decimal(c.max_mark, "max")) if ok else None
            parts.append({"name": name, "score": to_decimal(c.score, "score") if ok else None,
                          "max": to_decimal(c.max_mark, "max"), "pct": pct,
                          "status": "scored" if ok else ("missing" if c.status == MarkStatus.SCORED else c.status.value)})
            a = acc.setdefault(name, [Decimal(0), 0, 0]); a[2] += 1
            if pct is not None:
                a[0] += pct; a[1] += 1
        rows.append({"subject": e.subject, "parts": parts})
    summary = [{"name": n, "avg_pct": (a[0] / a[1]).quantize(Decimal("0.1"), ROUND_HALF_UP) if a[1] else None,
                "n": a[1], "of": a[2]} for n, a in acc.items()]
    return rows, summary


def _pos(res, sid) -> dict:
    p = res.ranks.get(sid)
    return {"pos": p, "of": res.population_size,
            "label": f"{p}/{res.population_size}" if p else f"—/{res.population_size}",
            "excluded": res.excluded.get(sid, "")}


class ReportService:
    def __init__(self, ds: DataSource, scheme: GradingScheme, config: Optional[ReportConfig] = None):
        self.ds, self.scheme, self.cfg = ds, scheme, config or ReportConfig()

    # ---------- authorization (tenancy first; 404 on foreign ids to avoid leaking existence)
    def authorize_student(self, user: User, student: Student):
        if student.school_id != user.school_id:
            raise NotFound("student")
        if user.role == "admin":
            return
        if user.role == "teacher" and ("*" in user.class_names or student.class_name in user.class_names):
            return
        if user.role in ("guardian", "student") and student.id in user.student_ids:
            return
        raise PermissionDenied("not permitted for this student")

    def authorize_class(self, user: User, class_name: str):
        if user.role == "admin" or (user.role == "teacher" and ("*" in user.class_names or class_name in user.class_names)):
            return
        raise PermissionDenied("not permitted for this class")

    # ---------- snapshot: full eligible population, never just the print selection
    def snapshot(self, user: User, exam_id: str, class_name: str) -> Snapshot:
        sid = user.school_id                      # tenant comes from the session, not the request
        exam = self.ds.get_exam(sid, exam_id)
        pop = self.ds.list_students(sid, class_name=class_name)
        if not pop:
            raise ReportNotReady("no_students", f"No students found in {class_name}.")
        summaries, cands, h = {}, [], hashlib.sha256()
        for s in pop:
            ents = self.ds.get_entries(sid, exam_id, s.id)
            summ = evaluate_student(ents, self.scheme)
            summaries[s.id] = summ
            for r in summ.subjects:
                h.update(f"{s.id}|{r.subject}|{r.status}|{r.score}".encode())
            val = None
            if summ.subjects_completed:
                val = (summ.best_points * 100000 + summ.total) if self.cfg.rank_by == "best_points" else summ.total
            cands.append(Candidate(s.id, val, summ.is_complete, s.status, group=s.stream))
        pol, inc = self.cfg.tie_policy, self.cfg.include_incomplete_in_rank
        overall = rank(cands, population=f"{class_name} overall", tie_policy=pol, include_incomplete=inc)
        streams = sorted({s.stream for s in pop})
        stream_r = {st: rank(cands, population=f"{class_name} {st}", tie_policy=pol,
                             include_incomplete=inc, group=st) for st in streams}
        by_id = {s.id: s for s in pop}
        gender_r = {}
        for st in streams:
            for g in sorted({s.gender for s in pop if s.stream == st}):
                sub = [c for c in cands if c.group == st and by_id[c.student_id].gender == g]
                gender_r[(st, g)] = rank(sub, population=f"{class_name} {st} gender {g}", tie_policy=pol,
                                         include_incomplete=inc)
        subj_r = {}
        subjects = sorted({r.subject for sm in summaries.values() for r in sm.subjects})
        scopes = streams if self.cfg.subject_rank_scope == "stream" else ["*"]
        for sc in scopes:
            for sub in subjects:
                cs = []
                for s in pop:
                    if sc != "*" and s.stream != sc: continue
                    r = next((x for x in summaries[s.id].subjects if x.subject == sub), None)
                    cs.append(Candidate(s.id, r.score if r and r.counted else None, True, s.status))
                subj_r[(sc, sub)] = rank(cs, population=f"{class_name} {sc} {sub}", tie_policy=pol)
        return Snapshot(sid, exam, class_name, by_id, summaries, overall, stream_r, gender_r, subj_r,
                        h.hexdigest()[:16])

    # ---------- validation
    def check_ready(self, snap: Snapshot, student: Student, force_provisional: Optional[bool] = None):
        summ = snap.summaries.get(student.id)
        if summ is None or student.class_name != snap.class_name:
            raise ReportNotReady("not_in_class", "Student does not belong to the selected class for this exam.")
        if self.cfg.require_published and not snap.exam.published:
            raise ReportNotReady("unpublished", "Results for this examination are not published yet.")
        if student.status != "active":
            raise ReportNotReady("withdrawn", "Student is withdrawn and has no report for this exam.")
        if summ.subjects_completed == 0:
            raise ReportNotReady("no_results", "No results recorded for this student.")
        if not summ.is_complete:
            allow = self.cfg.allow_provisional if force_provisional is None else force_provisional
            if not (allow and self.cfg.allow_provisional):
                raise ReportNotReady("incomplete", f"{summ.pending} result(s) still pending; "
                                     "enable provisional reports to generate anyway.")
            return True
        return False

    # ---------- assembly
    def build_report(self, *args, **kwargs):
        rd = self._build_report_core(*args, **kwargs)
        rd.scale = self._scale()
        rd.labels = dict(self.cfg.labels)
        return rd

    def _scale(self):
        """Chart ticks from the scheme itself: top, 75%, 50%, 25%, bottom points."""
        sc = self.scheme
        mx = sc.max_points
        mn = min(b.points for b in sc.bands)
        ticks, seen = [], set()
        for t in (mx, mx * Decimal("0.75"), mx * Decimal("0.5"), mx * Decimal("0.25"), mn):
            pt = int(t + Decimal("0.5"))
            lab = sc.label_for_points(Decimal(pt))
            if lab and pt not in seen:
                seen.add(pt)
                ticks.append((pt, lab))
        return {"max": float(mx), "ticks": ticks}

    def _rank_note(self):
        n = self.cfg.rank_note
        if self.scheme.best_n is None and "KCSE" in n:
            return "Position ranked by total points across all subjects (internal school ranking)"
        return n

    def _build_report_core(self, user: User, snap: Snapshot, student_id: str,
                     provisional_ok: Optional[bool] = None, today: Optional[date] = None) -> ReportData:
        student = self.ds.get_student(user.school_id, student_id)
        self.authorize_student(user, student)
        provisional = self.check_ready(snap, student, provisional_ok)
        summ = snap.summaries[student.id]
        school = self.ds.get_school(user.school_id)
        sid = student.id
        scope = student.stream if self.cfg.subject_rank_scope == "stream" else "*"
        lines = []
        for r in summ.subjects:
            res = snap.subject.get((scope, r.subject))
            pos = ""
            if res and r.counted:
                pos = f"{res.ranks.get(sid, '—')}/{res.population_size}"
            remark = r.remarks or (self.cfg.remark_for_pct(r.pct) if r.pct is not None else "")
            label = {"scored": "", "missing": "Pending", "absent": "Absent", "exempt": "Exempt",
                     "withdrawn": "Withdrawn"}[r.status]
            lines.append(SubjectLine(r.subject, r.status, r.score, r.max_mark, r.pct,
                                     r.grade or label or "—", r.points, pos, remark if r.counted else label, r.teacher))
        positions = {"stream": _pos(snap.stream[student.stream], sid),
                     "gender": _pos(snap.gender[(student.stream, student.gender)], sid),
                     "overall": _pos(snap.overall, sid)}
        history = self._history(user.school_id, snap.exam, student, summ)
        series = (self._subject_series(user.school_id, snap.exam, student, lines)
                  if self.cfg.sections.get("trend_insights") else None)
        remarks = self.ds.get_remarks(user.school_id, snap.exam.id, sid)
        warnings = list(summ.notes)
        if provisional:
            warnings.insert(0, "PROVISIONAL: results incomplete; rankings exclude incomplete students.")
        if not snap.exam.published:
            warnings.insert(0, "UNPUBLISHED results (preview only).")
        fee = self.ds.get_fee_note(user.school_id, sid) if (user.can_view_fees and self.cfg.sections.get("fees")) else None
        report_no = f"RPT-{snap.exam.year}-T{snap.exam.term}-{student.adm_no}"
        att_view = None
        if self.cfg.sections.get("attendance"):
            att_view = _attendance_view(self.ds.get_attendance(user.school_id, snap.exam.id, sid), warnings)
        bd_rows, bd_sum = [], []
        if self.cfg.sections.get("assessment_breakdown"):
            bd_rows, bd_sum = _breakdown(self.ds.get_entries(user.school_id, snap.exam.id, sid))
        return ReportData(
            report_no, school, student, snap.exam, (today or date.today()).strftime("%d %b %Y"), lines,
            summ.total, summ.max_total, summ.mean_points, summ.mean_points_grade or "—", summ.mean_pct,
            summ.best_points, summ.max_points, summ.subjects_completed, summ.pending, summ.excluded,
            positions, provisional, warnings, history, self._insight(lines, summ, history, series), remarks,
            {"closing": snap.exam.closing_date, "next_term": snap.exam.next_term_opens}, fee,
            snap.snapshot_id, sign(report_no, snap.snapshot_id), dict(self.cfg.sections), self._rank_note(),
            [(b.label, _range_label(b)) for b in sorted(self.scheme.bands, key=lambda b: -b.min_pct)], self.cfg.footer_note,
            att_view, bd_rows, bd_sum)

    def _history(self, school_id, exam, student, current: StudentSummary) -> list:
        out = []
        prior = [e for e in self.ds.list_exams(school_id) if e.sequence < exam.sequence and e.published]
        for e in prior[-(self.cfg.history_limit - 1):]:
            ents = self.ds.get_entries(school_id, e.id, student.id)
            sm = evaluate_student(ents, self.scheme) if ents else None
            ok = sm and sm.subjects_completed
            out.append({"exam": _short(e), "mean": sm.mean_points if ok else None,
                        "grade": (sm.mean_points_grade if ok else None) or "—"})
        out.append({"exam": _short(exam), "mean": current.mean_points, "grade": current.mean_points_grade or "—"})
        return out

    def _subject_series(self, school_id, exam, student, lines):
        """Per-subject REAL percentages over earlier published exams plus this one.
        Only scored marks are used; missing/absent/exempt are never turned into 0."""
        from .insights import Point
        series = {}
        n = max(self.cfg.history_limit - 1, 0)
        prior = [e for e in self.ds.list_exams(school_id) if e.sequence < exam.sequence and e.published]
        prior = prior[len(prior) - n:] if n else []
        for e in prior:
            ents = self.ds.get_entries(school_id, e.id, student.id)
            if not ents:
                continue
            sm = evaluate_student(ents, self.scheme)
            for r in sm.subjects:
                if r.status == "scored" and r.pct is not None:
                    series.setdefault(r.subject, []).append(Point(e.id, _short(e), e.sequence, r.pct))
        for l in lines:
            if l.status == "scored" and l.pct is not None:
                series.setdefault(l.subject, []).append(Point(exam.id, _short(exam), exam.sequence, l.pct))
        return series

    def _insight(self, lines, summ, history, series=None) -> dict:
        """Deterministic facts + rule-based advice. No marks, grades or comments are invented;
        an optional AI narrative must be advisory and teacher-reviewed (not wired here)."""
        scored = [l for l in lines if l.status == "scored"]
        facts = []
        if scored:
            top = sorted(scored, key=lambda l: (-l.pct, l.subject))[:self.cfg.strong_count]
            facts.append("Strongest: " + ", ".join(f"{l.subject} ({_num(l.score)}, {l.grade})" for l in top) + ".")
            weak = [l for l in scored if l.pct < Decimal(str(self.cfg.weak_pct))]
            if weak:
                facts.append("Below " + f"{self.cfg.weak_pct:g}%: " + ", ".join(l.subject for l in weak) + ".")
        prev = next((h for h in reversed(history[:-1]) if h["mean"] is not None), None)
        cur = history[-1]["mean"]
        if prev and cur is not None:
            d = cur - prev["mean"]
            word = "improved" if d > 0 else "dropped" if d < 0 else "stayed the same"
            facts.append(f"Mean points {word} from {prev['mean']:g} to {cur:g}" + (f" ({d:+g})." if d else "."))
        if summ.pending:
            facts.append(f"{summ.pending} result(s) pending.")
        rec = ""
        if summ.mean_points is not None:
            m = summ.mean_points
            rec = ("Performing well; keep the current study routine." if m >= self.scheme.max_points * Decimal("0.75") else
                   "Steady progress; target the weaker subjects." if m >= self.scheme.max_points * Decimal("0.5") else
                   "Needs focused support in the weaker subjects; closer follow-up is advised.")
        if series:
            from .insights import analyse_student, ranked_facts
            facts.extend(ranked_facts(analyse_student(series), self.cfg.trend_max_facts))
        if not self.cfg.sections.get("aggregate", True):
            facts = [f for f in facts if not f.startswith("Mean points")]
            rec = ""
        return {"facts": facts, "recommendation": rec, "source": "rules"}


def _num(d) -> str:
    d = Decimal(d)
    return format(d.normalize(), "f")


def _short(e: Exam) -> str:
    return f"END T{e.term}'{str(e.year)[2:]}" if "END" in e.name.upper() else f"T{e.term}'{str(e.year)[2:]}"


def _range_label(b) -> str:
    hi = b.max_pct if b.max_pct == 100 else b.max_pct - 1
    return f"{b.min_pct:g}–{hi:g}" if b.max_pct == b.max_pct.to_integral() else f"{b.min_pct:g}–<{b.max_pct:g}"
