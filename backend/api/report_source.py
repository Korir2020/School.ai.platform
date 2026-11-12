"""Django data source for the marian_reports module.

Maps Marian's own models onto the marian_reports DataSource interface.
Rules:
  * Every method is scoped to one school; a record from another school is
    reported as NotFound, never returned.
  * Only approved or locked marks count. Draft/submitted entries map to PENDING;
    a missing database row maps to MISSING. Zero remains a genuine scored mark.
    Absent, exempted, not-assessed and pending dispositions remain distinct.
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
    AttendanceRecord, Enrollment, Exam, LevelResult, Performance, ReportAuditEntry,
    ReportComment, ReportRemark, ReportSettings, School, Student,
    SubjectPaper, SubjectRegistration, TeacherAssignment, Term,
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
    return (perf.marks if perf is not None and perf.status in OFFICIAL
            and perf.mark_status == "scored" else None)


def _status(perf):
    if perf is None:
        return MarkStatus.MISSING
    if perf.status not in OFFICIAL:
        return MarkStatus.PENDING
    return {
        "scored": MarkStatus.SCORED,
        "absent": MarkStatus.ABSENT,
        "exempted": MarkStatus.EXEMPT,
        "not_assessed": MarkStatus.NOT_ASSESSED,
        "pending": MarkStatus.PENDING,
    }.get(perf.mark_status, MarkStatus.PENDING)


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
        ).select_related("term__academic_year", "class_level__curriculum").first()
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
                "class_level", "stream", "academic_year", "pathway"
        ).order_by("academic_year__start_date", "id"):
            latest[e.student_id] = e  # later years overwrite earlier ones
        return latest

    def _to_student(self, student, enrollment, registrations=()):
        return ReportStudent(
            id=str(student.pk), school_id=str(student.school_id),
            adm_no=student.admission_number,
            full_name=f"{student.first_name} {student.last_name}".strip(),
            gender="",
            class_name=enrollment.class_level.name if enrollment else "",
            stream=enrollment.stream.name if enrollment and enrollment.stream else "",
            kcpe_score=None, status="active",
            pathway_name=enrollment.pathway.name if enrollment and enrollment.pathway else "",
            pathway_code=enrollment.pathway.code if enrollment and enrollment.pathway else "",
            subject_combination=tuple(sorted(str(row[0]) for row in registrations)),
            registered_subject_names=tuple(sorted(row[1] for row in registrations)),
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
            framework_key=exam.framework_key,
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
            address=school.location, phone=school.phone, motto=school.motto,
            principal_name=school.principal_name, logo_path=logo,
        )

    def get_exam(self, school_id, exam_id):
        exam = self._exam_row(school_id, exam_id)
        if not exam.framework_key and exam.class_level.curriculum.code.upper() == "CBC":
            from api.framework_rules import resolve
            version = resolve(exam.school_id, exam.class_level, exam.term.academic_year)
            if version is not None:
                exam.framework_key = version.framework_key
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

    def list_exam_students(self, school_id, exam_id, class_name):
        """Exact Grade 1–9 CBC cohort; legacy and other frameworks keep their old population."""
        exam = self._exam_row(school_id, exam_id)
        framework_key = exam.framework_key
        if not framework_key and exam.class_level.curriculum.code.upper() == "CBC":
            from api.framework_rules import resolve
            version = resolve(exam.school_id, exam.class_level, exam.term.academic_year)
            framework_key = version.framework_key if version is not None else None
        from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS
        if framework_key not in CBC_REPORT_FRAMEWORKS:
            return None
        if exam.class_level.name != class_name:
            return []
        enrollments = Enrollment.objects.filter(
            student__school_id=_pk(school_id), student__status="active",
            academic_year_id=exam.term.academic_year_id,
            class_level_id=exam.class_level_id, is_active=True,
        ).select_related("student", "class_level", "stream", "pathway").order_by(
            "student__admission_number", "-id")
        registrations = defaultdict(list)
        for student_id, subject_id, subject_name in SubjectRegistration.objects.filter(
            student_id__in=[row.student_id for row in enrollments],
            academic_year_id=exam.term.academic_year_id,
            subject__school_id=_pk(school_id),
        ).values_list("student_id", "subject_id", "subject__name"):
            registrations[student_id].append((subject_id, subject_name))
        seen, out = set(), []
        for enrollment in enrollments:
            if enrollment.student_id in seen:
                continue
            seen.add(enrollment.student_id)
            out.append(self._to_student(
                enrollment.student, enrollment, registrations.get(enrollment.student_id, ())))
        return out

    def get_entries(self, school_id, exam_id, student_id):
        exam = self._exam_row(school_id, exam_id)
        student = self._student_row(school_id, student_id)
        return self.get_entries_for_students(
            school_id, exam_id, [student.pk], exam_row=exam,
        ).get(str(student.pk), [])

    def get_entries_for_students(self, school_id, exam_id, student_ids, exam_row=None):
        """Build a report-entry map with a bounded set of cohort-wide queries."""
        exam = exam_row or self._exam_row(school_id, exam_id)
        sid = _pk(school_id)
        ids = [_pk(student_id) for student_id in student_ids]
        students = list(Student.objects.filter(school_id=sid, pk__in=ids))
        if not students:
            return {}
        ids = [student.pk for student in students]

        enrollments = {}
        for enrollment in Enrollment.objects.filter(
            student_id__in=ids, academic_year_id=exam.term.academic_year_id,
        ).select_related("stream").order_by("-id"):
            enrollments.setdefault(enrollment.student_id, enrollment)

        subjects_by_student = defaultdict(dict)
        for registration in SubjectRegistration.objects.filter(
            student_id__in=ids, academic_year_id=exam.term.academic_year_id,
            subject__school_id=exam.school_id,
        ).select_related("subject"):
            subjects_by_student[registration.student_id][registration.subject_id] = registration.subject

        marks_by_student = defaultdict(lambda: defaultdict(dict))
        for mark in Performance.objects.filter(
            student_id__in=ids, term=exam.term,
            assessment_type=exam.assessment_type,
        ).select_related("subject"):
            marks_by_student[mark.student_id][mark.subject_id][mark.paper_number] = mark

        subject_ids = {
            subject_id for subjects in subjects_by_student.values()
            for subject_id in subjects
        }
        assignments_by_stream_subject = defaultdict(dict)
        stream_ids = {e.stream_id for e in enrollments.values() if e.stream_id}
        for assignment in TeacherAssignment.objects.filter(
            school_id=exam.school_id, stream_id__in=stream_ids,
            subject_id__in=subject_ids,
        ).select_related("teacher__user"):
            assignments_by_stream_subject[(assignment.stream_id, assignment.subject_id)].setdefault(
                assignment.subject_id,
                assignment.teacher.user.get_full_name().strip(),
            )

        papers_by_subject = defaultdict(list)
        for paper in SubjectPaper.objects.filter(
            subject_id__in=subject_ids,
        ).order_by("paper_number"):
            papers_by_subject[paper.subject_id].append(paper)

        achievement_by_student_subject = {}
        from marian_reports.frameworks import CBC_REPORT_FRAMEWORKS
        is_cbc_level_stage = exam.framework_key in CBC_REPORT_FRAMEWORKS
        if is_cbc_level_stage and subject_ids:
            for level in LevelResult.objects.filter(
                student_id__in=ids, subject_id__in=subject_ids,
                academic_year_id=exam.term.academic_year_id, term=exam.term,
                assessment_type=exam.assessment_type, status__in=OFFICIAL,
            ).select_related("scale"):
                descriptor = next((item for item in level.scale.levels
                                   if item.get("key") == level.level_key), None)
                if descriptor is None:
                    continue
                label = descriptor.get("label", level.level_key)
                description = descriptor.get("description", "").strip()
                text = "Achievement: " + label
                if description:
                    text += " — " + description
                if level.comment:
                    text += " | " + level.comment
                achievement_by_student_subject[(level.student_id, level.subject_id)] = text

        result = {}
        for student in students:
            subjects = subjects_by_student.get(student.pk, {})
            enrollment = enrollments.get(student.pk)
            stream_id = enrollment.stream_id if enrollment else None
            entries = []
            for subject_id, subject in sorted(
                subjects.items(), key=lambda item: item[1].name,
            ):
                got = marks_by_student[student.pk].get(subject_id, {})
                teacher = assignments_by_stream_subject.get(
                    (stream_id, subject_id), {},
                ).get(subject_id, "")
                achievement = achievement_by_student_subject.get(
                    (student.pk, subject_id), "")
                subject_papers = papers_by_subject.get(subject_id, [])
                if subject_papers:
                    components = tuple(
                        Component(
                            score=_score(got.get(paper.paper_number)),
                            max_mark=paper.max_marks, weight=paper.weight,
                            status=_status(got.get(paper.paper_number)),
                            name=f"Paper {paper.paper_number}",
                        ) for paper in subject_papers
                    )
                    entries.append(SubjectEntry(
                        subject=subject.name, max_mark=HUNDRED,
                        components=components, teacher=teacher, remarks=achievement,
                    ))
                else:
                    mark = got.get(1)
                    entries.append(SubjectEntry(
                        subject=subject.name, max_mark=HUNDRED,
                        score=_score(mark), status=_status(mark), teacher=teacher,
                        remarks=achievement,
                    ))
            result[str(student.pk)] = entries
        return result

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

    def saved_comment_templates(self):
        saved = self.saved_options().get("comment_templates", {})
        return saved if isinstance(saved, dict) else {}

    def save_comment_templates(self, body):
        self._require_school()
        options = self.saved_options()
        options["comment_templates"] = body if isinstance(body, dict) else {}
        ReportSettings.objects.update_or_create(
            school_id=self.school_id, defaults={"options": options})

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
