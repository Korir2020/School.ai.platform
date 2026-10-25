"""Django data source for the marian_reports module.

Maps Marian's own models onto the marian_reports DataSource interface.
Rules:
  * Every method is scoped to one school; a record from another school is
    reported as NotFound, never returned.
  * Only approved or locked marks count as scored. Draft, submitted and
    never-entered marks are MISSING (pending). A missing mark is never 0.
  * Paper weights come from SubjectPaper. A subject with no SubjectPaper rows
    is a simple single-mark subject using paper 1 (as exam_publish does).
  * Performance marks are capped at 100 in Marian, so max_mark is always 100.
  * Anything Marian does not store (gender, KCPE, principal, motto, remarks,
    fee notes) is returned empty. Nothing is invented.

marian_reports is imported here only, so the rest of the backend does not
depend on it until the report views are wired in.
"""
import re
import time
import uuid
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count

from marian_reports.domain import (
    Attendance, DataSource, NotFound,
    Exam as ReportExam, School as ReportSchool, Student as ReportStudent,
)
from marian_reports.audit import AuditAccessDenied, AuditEntry
from marian_reports.grading import (
    Component, MarkStatus, SubjectEntry, make_scheme,
)
from marian_reports.section_setup import apply_sections

from schools.models import (
    AttendanceRecord, Enrollment, Exam, Performance, ReportAuditEntry,
    ReportComment, ReportRemark, ReportSettings, School, Student,
    SubjectPaper, TeacherAssignment, Term,
)

OFFICIAL = ("approved", "locked")
HUNDRED = Decimal("100")
ASSESSMENT_ORDER = {"opener": 0, "mid": 1, "end": 2}


def _pk(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise NotFound("not found")


def _score(perf):
    return perf.marks if perf is not None and perf.status in OFFICIAL else None


def _status(perf):
    return MarkStatus.SCORED if _score(perf) is not None else MarkStatus.MISSING


def _term_number(term, same_year_terms):
    found = re.search(r"\d+", term.name)
    if found:
        return int(found.group())
    ids = [t.id for t in same_year_terms]
    return ids.index(term.id) + 1 if term.id in ids else 0


def _year_number(academic_year):
    found = re.search(r"\d{4}", academic_year.name)
    return int(found.group()) if found else academic_year.start_date.year


class DjangoDataSource(DataSource):
    # ---- helpers -------------------------------------------------------
    def _school_row(self, school_id):
        row = School.objects.filter(pk=_pk(school_id)).first()
        if row is None:
            raise NotFound("not found")
        return row

    def _student_row(self, school_id, student_id):
        row = Student.objects.filter(
            pk=_pk(student_id), school_id=_pk(school_id)).first()
        if row is None:
            raise NotFound("not found")
        return row

    def _exam_row(self, school_id, exam_id):
        row = Exam.objects.filter(
            pk=_pk(exam_id), school_id=_pk(school_id),
        ).select_related("term__academic_year", "class_level").first()
        if row is None:
            raise NotFound("not found")
        return row

    def _school_terms(self, school_id):
        return list(
            Term.objects.filter(academic_year__school_id=_pk(school_id))
            .select_related("academic_year").order_by("start_date", "id"))

    def _latest_enrollments(self, school_id, student_ids=None):
        rows = Enrollment.objects.filter(student__school_id=_pk(school_id))
        if student_ids is not None:
            rows = rows.filter(student_id__in=student_ids)
        latest = {}
        for e in rows.select_related(
                "class_level", "stream", "academic_year"
        ).order_by("academic_year__start_date", "id"):
            latest[e.student_id] = e  # later years overwrite earlier ones
        return latest

    def _to_student(self, student, enrollment):
        return ReportStudent(
            id=str(student.pk), school_id=str(student.school_id),
            adm_no=student.admission_number,
            full_name=f"{student.first_name} {student.last_name}".strip(),
            gender="",
            class_name=enrollment.class_level.name if enrollment else "",
            stream=enrollment.stream.name if enrollment and enrollment.stream else "",
            kcpe_score=None, status="active",
        )

    def _to_exam(self, exam, terms):
        term = exam.term
        same_year = [t for t in terms if t.academic_year_id == term.academic_year_id]
        later = [t for t in terms if t.start_date > term.end_date]
        return ReportExam(
            id=str(exam.pk), school_id=str(exam.school_id), name=exam.name,
            term=_term_number(term, same_year),
            year=_year_number(term.academic_year),
            published=exam.status == "published",
            sequence=term.start_date.toordinal() * 10
            + ASSESSMENT_ORDER.get(exam.assessment_type, 0),
            closing_date=term.end_date.isoformat(),
            next_term_opens=later[0].start_date.isoformat() if later else "",
        )

    # ---- DataSource ----------------------------------------------------
    def get_school(self, school_id):
        school = self._school_row(school_id)
        try:
            logo = school.logo.path if school.logo else None
        except (ValueError, NotImplementedError):
            logo = None
        return ReportSchool(
            id=str(school.pk), name=school.name, short_name=school.name,
            address=school.location, phone=school.phone, motto="",
            principal_name="", logo_path=logo,
        )

    def get_exam(self, school_id, exam_id):
        exam = self._exam_row(school_id, exam_id)
        return self._to_exam(exam, self._school_terms(school_id))

    def list_exams(self, school_id):
        exams = Exam.objects.filter(school_id=_pk(school_id)).select_related(
            "term__academic_year", "class_level").order_by("id")
        terms = self._school_terms(school_id)
        return [self._to_exam(e, terms) for e in exams]

    def get_student(self, school_id, student_id):
        student = self._student_row(school_id, student_id)
        enrollment = self._latest_enrollments(school_id, [student.pk]).get(student.pk)
        return self._to_student(student, enrollment)

    def list_students(self, school_id, class_name=None, stream=None):
        students = list(Student.objects.filter(
            school_id=_pk(school_id)).order_by("admission_number"))
        enrolled = self._latest_enrollments(school_id, [s.pk for s in students])
        out = []
        for s in students:
            item = self._to_student(s, enrolled.get(s.pk))
            if class_name is not None and item.class_name != class_name:
                continue
            if stream is not None and item.stream != stream:
                continue
            out.append(item)
        return out

    def get_entries(self, school_id, exam_id, student_id):
        exam = self._exam_row(school_id, exam_id)
        student = self._student_row(school_id, student_id)
        marks = Performance.objects.filter(
            student=student, term=exam.term, assessment_type=exam.assessment_type,
        ).select_related("subject")
        by_subject, subjects = defaultdict(dict), {}
        for m in marks:
            by_subject[m.subject_id][m.paper_number] = m
            subjects[m.subject_id] = m.subject
        # Subjects assigned to the student's stream are expected even when
        # nothing has been entered yet: they show as pending, not omitted.
        enrollment = Enrollment.objects.filter(
            student=student, academic_year=exam.term.academic_year,
        ).order_by("-id").first()
        teacher_of = {}
        if enrollment and enrollment.stream_id:
            assigned = TeacherAssignment.objects.filter(
                school_id=exam.school_id, stream_id=enrollment.stream_id,
            ).select_related("subject", "teacher__user")
            for a in assigned:
                subjects.setdefault(a.subject_id, a.subject)
                teacher_of.setdefault(
                    a.subject_id, a.teacher.user.get_full_name().strip())
        papers = defaultdict(list)
        for sp in SubjectPaper.objects.filter(
                subject_id__in=subjects).order_by("paper_number"):
            papers[sp.subject_id].append(sp)
        entries = []
        for subject_id, subject in sorted(
                subjects.items(), key=lambda kv: kv[1].name):
            got = by_subject.get(subject_id, {})
            teacher = teacher_of.get(subject_id, "")
            if papers.get(subject_id):
                components = tuple(
                    Component(
                        score=_score(got.get(p.paper_number)), max_mark=p.max_marks,
                        weight=p.weight, status=_status(got.get(p.paper_number)),
                        name=f"Paper {p.paper_number}")
                    for p in papers[subject_id])
                entries.append(SubjectEntry(
                    subject=subject.name, max_mark=HUNDRED,
                    components=components, teacher=teacher))
            else:
                perf = got.get(1)
                entries.append(SubjectEntry(
                    subject=subject.name, max_mark=HUNDRED, score=_score(perf),
                    status=_status(perf), teacher=teacher))
        return entries

    def get_remarks(self, school_id, exam_id, student_id):
        # Only teacher-approved text is ever stored (see DjangoRemarkStore).
        exam = self._exam_row(school_id, exam_id)
        student = self._student_row(school_id, student_id)
        found = {
            r.field: r.text for r in ReportRemark.objects.filter(
                school_id=exam.school_id, exam=exam, student=student)
        }
        # No approved comment: fall back to a default from the overall
        # average (published result). A teacher's approved text always wins.
        from marian_reports.config import ReportConfig
        from schools.models import ExamResult
        res = ExamResult.objects.filter(exam=exam, student=student).first()
        if res is not None:
            text = ReportConfig().remark_for_pct(float(res.overall_average))
            if text:
                for key in ("class_teacher", "principal"):
                    found.setdefault(key, text)
        return found

    def get_fee_note(self, school_id, student_id):
        self._student_row(school_id, student_id)
        return None

    def get_attendance(self, school_id, exam_id, student_id):
        exam = self._exam_row(school_id, exam_id)
        student = self._student_row(school_id, student_id)
        window = (exam.term.start_date, exam.term.end_date)
        counts = {
            r["status"]: r["n"]
            for r in AttendanceRecord.objects.filter(
                student=student, date__range=window,
            ).order_by().values("status").annotate(n=Count("id"))
        }
        if not counts:
            return None  # nothing recorded: the section is omitted
        days_open = AttendanceRecord.objects.filter(
            student__school_id=exam.school_id, date__range=window,
        ).order_by().values("date").distinct().count()
        late = counts.get("late", 0)
        # Late learners attended, so they count as present; excused days are
        # recorded but are neither present nor absent here (policy undecided).
        return Attendance(
            days_open=days_open,
            days_present=counts.get("present", 0) + late,
            days_absent=counts.get("absent", 0),
            days_late=late,
        )


class DjangoRemarkStore:
    # Callbacks for marian_reports CommentService (set_remark / clear_remark).
    # They fire only on approval, so this table holds approved text only.
    # The school comes from the exam; a student of another school is refused.
    def set_remark(self, exam_id, student_id, field, text):
        if field not in dict(ReportRemark.FIELDS):
            raise ValueError("unknown remark field")
        exam = Exam.objects.filter(pk=_pk(exam_id)).first()
        student = Student.objects.filter(pk=_pk(student_id)).first()
        if exam is None or student is None or exam.school_id != student.school_id:
            raise NotFound("not found")
        ReportRemark.objects.update_or_create(
            exam=exam, student=student, field=field,
            defaults={"school_id": exam.school_id, "text": text})

    def clear_remark(self, exam_id, student_id, field):
        ReportRemark.objects.filter(
            exam_id=_pk(exam_id), student_id=_pk(student_id), field=field).delete()


class DjangoCommentStore:
    # Durable storage for marian_reports CommentService (draft and approved rows).
    # Make one per request, bound to the signed-in user's school. It refuses any
    # row, exam or student that does not belong to that school.
    def __init__(self, school_id):
        self.school_id = _pk(school_id)

    def load(self):
        out = {}
        for c in ReportComment.objects.filter(school_id=self.school_id):
            out[c.id] = {
                "id": c.id, "school_id": str(c.school_id),
                "exam_id": str(c.exam_id), "student_id": str(c.student_id),
                "class_name": c.class_name, "field": c.field, "text": c.text,
                "status": c.status, "source": c.source, "edited": c.edited,
                "approved_by": c.approved_by, "created_by": c.created_by,
                "at": c.at,
            }
        return out

    def save(self, row):
        if str(row["school_id"]) != str(self.school_id):
            raise NotFound("not found")
        exam = Exam.objects.filter(
            pk=_pk(row["exam_id"]), school_id=self.school_id).first()
        student = Student.objects.filter(
            pk=_pk(row["student_id"]), school_id=self.school_id).first()
        if exam is None or student is None:
            raise NotFound("not found")
        if ReportComment.objects.filter(id=row["id"]).exclude(
                school_id=self.school_id).exists():
            raise NotFound("not found")
        ReportComment.objects.update_or_create(id=row["id"], defaults={
            "school_id": self.school_id, "exam": exam, "student": student,
            "class_name": row["class_name"], "field": row["field"],
            "text": row["text"], "status": row["status"],
            "source": row["source"], "edited": bool(row.get("edited", False)),
            "approved_by": str(row.get("approved_by", "")),
            "created_by": str(row.get("created_by", "")),
            "at": float(row["at"]),
        })

    def delete(self, cid):
        ReportComment.objects.filter(id=cid, school_id=self.school_id).delete()


def scheme_to_dict(scheme):
    # Same shape the grading-config API returns.
    return {
        "bands": [[b.label, str(b.min_pct), str(b.max_pct), str(b.points)]
                  for b in scheme.bands],
        "pass_pct": str(scheme.pass_pct), "decimals": scheme.decimals,
        "rounding": scheme.rounding, "mean_rule": scheme.mean_rule,
        "absent_policy": scheme.absent_policy, "best_n": scheme.best_n,
    }


def scheme_from_dict(d):
    # Same call the grading-config PUT makes, so saved data is re-validated.
    return make_scheme(
        [tuple(x) for x in d["bands"]], pass_pct=d.get("pass_pct", 40),
        decimals=int(d.get("decimals", 2)), rounding=d.get("rounding", "half_up"),
        mean_rule=d.get("mean_rule", "total_over_max"),
        absent_policy=d.get("absent_policy", "pending"), best_n=d.get("best_n"))


class DjangoConfigStore:
    # Per-school grading scheme and section toggles. Bound to one school.
    def __init__(self, school_id):
        self.school_id = _pk(school_id)

    def _require_school(self):
        if not School.objects.filter(pk=self.school_id).exists():
            raise NotFound("not found")

    def _row(self):
        return ReportSettings.objects.filter(school_id=self.school_id).first()

    def load_scheme(self):
        row = self._row()
        return scheme_from_dict(row.grading) if row and row.grading else None

    def save_scheme(self, scheme):
        self._require_school()
        ReportSettings.objects.update_or_create(
            school_id=self.school_id,
            defaults={"grading": scheme_to_dict(scheme)})

    def saved_sections(self):
        row = self._row()
        return dict(row.sections) if row else {}

    def save_sections(self, body):
        self._require_school()
        merged = {**self.saved_sections(), **body}
        ReportSettings.objects.update_or_create(
            school_id=self.school_id, defaults={"sections": merged})

    def saved_options(self):
        row = self._row()
        return dict(row.options) if row and row.options else {}

    def save_options(self, body):
        self._require_school()
        merged = {**self.saved_options(), **body}
        merged = {k: v for k, v in merged.items() if v is not None}
        ReportSettings.objects.update_or_create(
            school_id=self.school_id, defaults={"options": merged})

    def apply_to(self, cfg):
        from api.report_options import apply_options
        saved = self.saved_sections()
        if saved:
            apply_sections(cfg, {"sections": saved})
        apply_options(cfg, self.saved_options())


class DjangoAuditLog:
    # Same interface and rules as marian_reports.audit.AuditLog, but durable:
    # admin only, own school only, newest first.
    def record(self, user, action, target="", detail=None):
        sid = _pk(user.school_id)
        if not School.objects.filter(pk=sid).exists():
            raise NotFound("not found")
        e = AuditEntry(uuid.uuid4().hex, time.time(), str(sid), user.id,
                       user.role, action, target, dict(detail or {}))
        ReportAuditEntry.objects.create(
            id=e.id, at=e.at, school_id=sid, user_id=str(e.user_id),
            role=e.role, action=e.action, target=e.target, detail=e.detail)
        return e

    def entries(self, user, action=None, limit=100):
        if user.role != "admin":
            raise AuditAccessDenied("admin only")
        rows = ReportAuditEntry.objects.filter(school_id=_pk(user.school_id))
        if action:
            rows = rows.filter(action=action)
        return [{
            "id": r.id, "at": r.at, "school_id": str(r.school_id),
            "user_id": r.user_id, "role": r.role, "action": r.action,
            "target": r.target, "detail": r.detail,
        } for r in rows.order_by("-at")[:limit]]
