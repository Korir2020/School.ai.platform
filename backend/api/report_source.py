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
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count

from marian_reports.domain import (
    Attendance, DataSource, NotFound,
    Exam as ReportExam, School as ReportSchool, Student as ReportStudent,
)
from marian_reports.grading import Component, MarkStatus, SubjectEntry

from schools.models import (
    AttendanceRecord, Enrollment, Exam, Performance, School, Student,
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
                        score=_score(got.get(p.paper_number)), max_mark=HUNDRED,
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
        # Marian has no remarks store yet; checks tenancy, returns nothing.
        self._exam_row(school_id, exam_id)
        self._student_row(school_id, student_id)
        return {}

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
