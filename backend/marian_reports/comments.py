"""Teacher-approved comments. AI (or a teacher) drafts; only approved text is printed."""
from __future__ import annotations

import threading
import time
import uuid

from .domain import NotFound, PermissionDenied

FIELDS = {"class_teacher": "class teacher", "principal": "principal"}
MAX_LEN = 400


class CommentError(ValueError):
    pass


class AINotConfigured(RuntimeError):
    pass


def build_prompt(rows, field):
    """Minimum data only: subject, percent, level. No names, ids, stream or gender."""
    lines = [f"- {r['subject']}: {r['pct']}% ({r['level']})" for r in rows]
    return ("Write a short, kind, factual report-card comment of at most two sentences "
            f"from the {FIELDS[field]}. Use only the results below. Do not invent facts, "
            "do not mention any name, and do not compare with other learners.\n"
            + "\n".join(lines))


def _clean(text):
    if not isinstance(text, str) or not text.strip():
        raise CommentError("Comment text is required.")
    text = " ".join(text.split())
    if len(text) > MAX_LEN:
        raise CommentError(f"Comment is too long (max {MAX_LEN} characters).")
    return text


def _label(row):
    if row["source"] != "ai":
        return "Teacher-written" + ("" if row["status"] == "approved" else " - not yet approved")
    if row["status"] == "approved":
        return "AI-drafted, teacher-approved"
    return "AI-drafted - review before approval"


def _public(row):
    keys = ("id", "exam_id", "student_id", "class_name", "field", "text", "status",
            "source", "edited", "approved_by")
    out = {k: row[k] for k in keys}
    out["label"] = _label(row)
    return out


class CommentService:
    def __init__(self, ds, svc, audit, set_remark, clear_remark, drafter=None, store=None):
        self.ds, self.svc, self.audit = ds, svc, audit
        self._set, self._clear, self.drafter = set_remark, clear_remark, drafter
        self.store = store
        self._rows = dict(store.load()) if store is not None else {}
        self._lock = threading.RLock()

    # ---- checks
    def _staff(self, user):
        if user.role not in ("admin", "teacher"):
            raise PermissionDenied("only teachers and admins can work on comments")

    def _check(self, user, class_name, field):
        self._staff(user)
        if field not in FIELDS:
            raise CommentError("field must be one of: " + ", ".join(sorted(FIELDS)))
        self.svc.authorize_class(user, class_name)
        if field == "principal" and user.role != "admin":
            raise PermissionDenied("principal comments: admin only")

    def _persist(self, row):
        if self.store is not None:
            self.store.save(row)

    def _forget(self, cid):
        if self.store is not None:
            self.store.delete(cid)

    def _get(self, user, cid):
        row = self._rows.get(cid)
        if not row or row["school_id"] != user.school_id:
            raise NotFound("comment")
        self._check(user, row["class_name"], row["field"])
        return row

    def _key(self, row):
        return (row["school_id"], row["exam_id"], row["student_id"], row["field"])

    def _log(self, user, action, row, **extra):
        self.audit.record(user, action, row["id"],
                          {"exam_id": row["exam_id"], "student_id": row["student_id"],
                           "field": row["field"], "source": row["source"],
                           "class_name": row["class_name"], **extra})

    # ---- AI drafting (minimum data only)
    def _ai_text(self, user, exam_id, student, field):
        if self.drafter is None:
            raise AINotConfigured("AI drafting is not set up. Write the comment yourself, "
                                  "or ask the administrator to connect a drafter.")
        snap = self.svc.snapshot(user, exam_id, student.class_name)
        summ = snap.summaries.get(student.id)
        rows = []
        if summ is not None:
            rows = [{"subject": r.subject, "pct": round(float(r.pct), 1), "level": r.grade or "-"}
                    for r in summ.subjects if r.pct is not None]
        if not rows:
            raise CommentError("There are no scored subjects yet to base a comment on.")
        try:
            out = self.drafter(build_prompt(rows, field))
        except Exception:
            raise CommentError("The AI drafter failed. Write the comment yourself or try again.")
        return _clean(out)

    # ---- workflow
    def draft(self, user, exam_id, student_id, field, text=None):
        self._staff(user)
        self.ds.get_exam(user.school_id, exam_id)
        student = self.ds.get_student(user.school_id, student_id)
        self._check(user, student.class_name, field)
        if text is None:
            text, source = self._ai_text(user, exam_id, student, field), "ai"
        else:
            text, source = _clean(text), "teacher"
        row = {"id": uuid.uuid4().hex, "school_id": user.school_id, "exam_id": exam_id,
               "student_id": student.id, "class_name": student.class_name, "field": field,
               "text": text, "status": "draft", "source": source, "edited": False,
               "approved_by": "", "created_by": user.id, "at": time.time()}
        with self._lock:
            for k, r in list(self._rows.items()):
                if self._key(r) == self._key(row) and r["status"] == "draft":
                    del self._rows[k]; self._forget(k)
            self._rows[row["id"]] = row; self._persist(row)
        self._log(user, "comment.drafted", row)
        return _public(row)

    def edit(self, user, cid, text):
        with self._lock:
            row = self._get(user, cid)
            text = _clean(text)
            was_approved = row["status"] == "approved"
            if was_approved:
                for k, r in list(self._rows.items()):
                    if k != cid and self._key(r) == self._key(row) and r["status"] == "draft":
                        del self._rows[k]; self._forget(k)
                self._clear(row["exam_id"], row["student_id"], row["field"])
                row["status"], row["approved_by"] = "draft", ""
            row["text"], row["edited"] = text, True; self._persist(row)
        self._log(user, "comment.edited", row, was_approved=was_approved)
        return _public(row)

    def approve(self, user, cid):
        with self._lock:
            row = self._get(user, cid)
            if row["status"] != "draft":
                raise CommentError("This comment is already approved.")
            for k, r in list(self._rows.items()):
                if k != cid and self._key(r) == self._key(row) and r["status"] == "approved":
                    del self._rows[k]; self._forget(k)
            row["status"], row["approved_by"] = "approved", user.id
            self._set(row["exam_id"], row["student_id"], row["field"], row["text"]); self._persist(row)
        self._log(user, "comment.approved", row)
        return _public(row)

    def reject(self, user, cid):
        with self._lock:
            row = self._get(user, cid)
            if row["status"] != "draft":
                raise CommentError("Approved comments cannot be rejected. Edit it first.")
            del self._rows[cid]; self._forget(cid)
        self._log(user, "comment.rejected", row)
        return _public(row)

    def listing(self, user, exam_id, class_name):
        self._staff(user)
        self.svc.authorize_class(user, class_name)
        ids = {s.id for s in self.ds.list_students(user.school_id, class_name=class_name)}
        with self._lock:
            rows = [r for r in self._rows.values()
                    if r["school_id"] == user.school_id and r["student_id"] in ids
                    and (not exam_id or r["exam_id"] == exam_id)]
        return [_public(r) for r in sorted(rows, key=lambda r: r["at"])]
