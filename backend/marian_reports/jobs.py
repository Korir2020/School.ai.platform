"""Background batch generation with idempotency, progress, failure capture and retry.
In-process thread pool for the standalone module; in Marian replace the executor with Celery/RQ
and persist Job rows (same interface)."""
from __future__ import annotations
import hashlib, io, json, os, shutil, tempfile, threading, time, uuid, zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional
from .domain import *
from .pdf import report_pdf, combined_pdf
import re


def _slug(s): return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


@dataclass
class Job:
    id: str; key: str; user_id: str; school_id: str; exam_id: str; class_name: str
    student_ids: list; options: dict
    status: str = "queued"          # queued | running | done | done_with_errors | failed
    done: int = 0; total: int = 0
    failures: dict = field(default_factory=dict)       # student_id -> message
    files: dict = field(default_factory=dict)          # public name -> path (private dir)
    manifest: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    error: str = ""

    def public(self) -> dict:
        return {"id": self.id, "status": self.status, "done": self.done, "total": self.total,
                "failures": dict(self.failures), "files": sorted(self.files), "manifest": self.manifest, "error": self.error}


class BatchManager:
    def __init__(self, service, out_dir: Optional[str] = None, workers: int = 2, verify_base="http://localhost:5000"):
        self.svc, self.verify_base = service, verify_base
        self.out_dir = out_dir or tempfile.mkdtemp(prefix="marian_reports_")   # private, never served statically
        os.makedirs(self.out_dir, mode=0o700, exist_ok=True)
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.jobs: dict = {}; self.lock = threading.Lock()

    @staticmethod
    def make_key(user, exam_id, class_name, student_ids, options) -> str:
        raw = json.dumps([user.school_id, user.id, exam_id, class_name, sorted(student_ids), options], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def submit(self, user: User, exam_id: str, class_name: str, student_ids: list, options: dict) -> tuple:
        """Returns (job, created). Identical in-flight/recent requests return the existing job (no duplicates)."""
        if not student_ids: raise ReportNotReady("empty_selection", "No students selected.")
        if len(student_ids) > self.svc.cfg.max_batch:
            raise ReportNotReady("batch_too_large", f"Batch limit is {self.svc.cfg.max_batch} reports.")
        self.svc.authorize_class(user, class_name)
        key = self.make_key(user, exam_id, class_name, student_ids, options)
        with self.lock:
            for j in self.jobs.values():
                if j.key == key and j.status in ("queued", "running", "done", "done_with_errors"):
                    return j, False
            job = Job(uuid.uuid4().hex, key, user.id, user.school_id, exam_id, class_name, list(student_ids), dict(options),
                      total=len(student_ids))
            self.jobs[job.id] = job
        self.pool.submit(self._run, job, user, list(student_ids))
        return job, True

    def get(self, user: User, job_id: str) -> Job:
        j = self.jobs.get(job_id)
        if not j or j.school_id != user.school_id or (j.user_id != user.id and user.role != "admin"):
            raise NotFound("job")
        return j

    def history(self, user: User, limit: int = 50) -> list:
        """Batch history for the user's school; admins see all, others only their own."""
        with self.lock:
            rows = [x for x in self.jobs.values() if x.school_id == user.school_id
                    and (user.role == "admin" or x.user_id == user.id)]
        rows.sort(key=lambda x: x.created, reverse=True)
        return [{"id": x.id, "status": x.status, "exam_id": x.exam_id,
                 "class_name": x.class_name, "user_id": x.user_id, "done": x.done,
                 "total": x.total, "failed": len(x.failures), "created": x.created}
                for x in rows[:limit]]

    def retry(self, user: User, job_id: str) -> Job:
        j = self.get(user, job_id)
        if not j.failures: return j
        ids = list(j.failures); j.failures = {}; j.status = "queued"; j.done = j.total - len(ids)
        self.pool.submit(self._run, j, user, ids, True)
        return j

    def wait(self, job: Job, timeout=60):
        t0 = time.time()
        while job.status in ("queued", "running") and time.time() - t0 < timeout: time.sleep(0.02)
        return job

    # ---------------------------------------------------------------- worker
    def _run(self, job: Job, user: User, ids: list, retry=False):
        job.status = "running"
        try:
            snap = self.svc.snapshot(user, job.exam_id, job.class_name)       # FULL population, one consistent snapshot
            prov = job.options.get("provisional")
            ok = getattr(job, "_ok", {}) if retry else {}
            for sid in ids:
                try:
                    rd = self.svc.build_report(user, snap, sid, provisional_ok=prov)
                    pdf = report_pdf(rd, self.verify_base)               # validates + renders; raises on failure
                    ok[sid] = (rd, pdf)
                except Exception as e:                                    # per-student isolation; never a silent success
                    job.failures[sid] = getattr(e, "message", None) or str(e)
                job.done = len(ok) + len(job.failures)
            job._ok = ok
            self._write(job, user, ok)
            if not ok:
                job.status, job.error = "failed", "No reports could be generated."
            else:
                job.status = "done_with_errors" if job.failures else "done"
        except Exception as e:
            job.status = "failed"; job.error = getattr(e, "message", None) or str(e)

    def _write(self, job: Job, user: User, ok: dict):
        d = os.path.join(self.out_dir, job.id); shutil.rmtree(d, ignore_errors=True); os.makedirs(d, mode=0o700)
        school = self.svc.ds.get_school(user.school_id); exam = self.svc.ds.get_exam(user.school_id, job.exam_id)
        base = f"{_slug(school.short_name)}_{exam.year}_Term_{exam.term}_{_slug(job.class_name)}"
        order = sorted(ok.values(), key=lambda t: (t[0].student.stream, t[0].student.adm_no))
        files = {}
        group = job.options.get("group_by", "class")          # class | stream
        if order:
            groups = {}
            for rd, _ in order: groups.setdefault(rd.student.stream if group == "stream" else "", []).append(rd)
            for g, rds in groups.items():
                name = f"{base}{'_' + _slug(g) if g else ''}_Report_Cards.pdf"
                with open(os.path.join(d, name), "wb") as f: f.write(combined_pdf(rds, name, self.verify_base))
                files[name] = os.path.join(d, name)
            zname = f"{base}_Individual_Reports.zip"
            with zipfile.ZipFile(os.path.join(d, zname), "w", zipfile.ZIP_DEFLATED) as z:
                for rd, pdf in order: z.writestr(f"{rd.report_no}.pdf", pdf)     # no names in filenames
            files[zname] = os.path.join(d, zname)
        manifest = {"exam": exam.name, "exam_id": exam.id, "class": job.class_name, "requested": job.total,
                    "successful": len(ok), "failed": len(job.failures), "failures": dict(job.failures),
                    "provisional": bool(job.options.get("provisional")), "snapshot": order[0][0].snapshot_id if order else None,
                    "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
        mp = os.path.join(d, "manifest.json")
        with open(mp, "w") as f: json.dump(manifest, f, indent=2)
        files["manifest.json"] = mp
        job.files, job.manifest = files, manifest

    def cleanup(self, max_age_s=3600):
        now = time.time()
        for jid in [k for k, j in self.jobs.items() if now - j.created > max_age_s]:
            shutil.rmtree(os.path.join(self.out_dir, jid), ignore_errors=True); self.jobs.pop(jid, None)
