"""Tests for the marian_reports data source (api/report_source.py).

These run only when marian_reports is importable, for example:
    PYTHONPATH=~/marian-reports python manage.py test api.test_report_source
Otherwise the whole module is skipped, so the normal suite is unaffected.
"""
import unittest
from datetime import date
from decimal import Decimal

try:
    import marian_reports  # noqa: F401
except ImportError:
    raise unittest.SkipTest("marian_reports is not installed")

from django.contrib.auth import get_user_model
from django.test import TestCase

from marian_reports.domain import NotFound
from marian_reports.grading import MarkStatus

from schools.models import (
    AcademicYear, AttendanceRecord, ClassLevel, Curriculum, Enrollment, Exam,
    Performance, School, Stream, Student, Subject, SubjectPaper,
    TeacherAssignment, TeacherProfile, Term,
)
from api.report_source import DjangoDataSource


class SourceCase(TestCase):
    def setUp(self):
        self.ds = DjangoDataSource()
        cur = Curriculum.objects.create(name="CBC", code="CBC")
        self.level = ClassLevel.objects.create(
            curriculum=cur, name="Form 3", level_number=3)
        self.school = School.objects.create(
            name="Alpha School", code="ALPHA", location="Nairobi", phone="0700")
        self.other = School.objects.create(name="Beta School", code="BETA")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026",
            start_date=date(2026, 1, 5), end_date=date(2026, 11, 27))
        self.t2 = Term.objects.create(
            academic_year=self.year, name="Term 2",
            start_date=date(2026, 5, 4), end_date=date(2026, 8, 7))
        self.t3 = Term.objects.create(
            academic_year=self.year, name="Term 3",
            start_date=date(2026, 8, 31), end_date=date(2026, 10, 23))
        self.stream = Stream.objects.create(
            school=self.school, class_level=self.level, name="East")
        self.maths = Subject.objects.create(
            school=self.school, name="Mathematics", code="MAT")
        self.science = Subject.objects.create(
            school=self.school, name="Science", code="SCI")
        self.student = Student.objects.create(
            school=self.school, first_name="Amina", last_name="Otieno",
            admission_number="A-1")
        Enrollment.objects.create(
            student=self.student, academic_year=self.year,
            class_level=self.level, stream=self.stream)
        self.exam = Exam.objects.create(
            school=self.school, name="End Term 3", term=self.t3,
            assessment_type="end", class_level=self.level, status="published")

    def mark(self, subject, marks, status="approved", paper=1, term=None,
             kind="end", student=None):
        return Performance.objects.create(
            student=student or self.student, subject=subject,
            academic_year=self.year, term=term or self.t3,
            assessment_type=kind, paper_number=paper, marks=marks, status=status)

    def entries(self):
        return {e.subject: e for e in self.ds.get_entries(
            str(self.school.id), str(self.exam.id), str(self.student.id))}


class MappingTests(SourceCase):
    def test_school(self):
        s = self.ds.get_school(str(self.school.id))
        self.assertEqual((s.name, s.address, s.phone, s.motto, s.logo_path),
                         ("Alpha School", "Nairobi", "0700", "", None))

    def test_exam_fields_come_from_term_and_year(self):
        e = self.ds.get_exam(str(self.school.id), str(self.exam.id))
        self.assertEqual((e.term, e.year, e.published), (3, 2026, True))
        self.assertEqual(e.closing_date, "2026-10-23")
        self.assertEqual(e.next_term_opens, "")

    def test_next_term_opens_uses_the_following_term(self):
        e2 = Exam.objects.create(
            school=self.school, name="End Term 2", term=self.t2,
            assessment_type="end", class_level=self.level)
        e = self.ds.get_exam(str(self.school.id), str(e2.id))
        self.assertEqual((e.term, e.published, e.next_term_opens),
                         (2, False, "2026-08-31"))

    def test_assessments_sort_opener_mid_end_within_a_term(self):
        ids = {}
        for kind in ("end", "opener", "mid"):
            ids[kind] = Exam.objects.create(
                school=self.school, name=kind, term=self.t2,
                assessment_type=kind, class_level=self.level).id
        seq = {k: self.ds.get_exam(str(self.school.id), str(i)).sequence
               for k, i in ids.items()}
        self.assertLess(seq["opener"], seq["mid"])
        self.assertLess(seq["mid"], seq["end"])

    def test_student_fields_and_filters(self):
        s = self.ds.get_student(str(self.school.id), str(self.student.id))
        self.assertEqual((s.adm_no, s.full_name, s.class_name, s.stream),
                         ("A-1", "Amina Otieno", "Form 3", "East"))
        self.assertEqual((s.gender, s.kcpe_score, s.status), ("", None, "active"))
        sid = str(self.school.id)
        self.assertEqual(len(self.ds.list_students(sid, "Form 3", "East")), 1)
        self.assertEqual(self.ds.list_students(sid, "Form 4"), [])
        self.assertEqual(self.ds.list_students(sid, "Form 3", "West"), [])

    def test_list_exams(self):
        self.assertEqual(len(self.ds.list_exams(str(self.school.id))), 1)

    def test_remarks_and_fee_note_are_empty_not_invented(self):
        sid, eid, st = (str(self.school.id), str(self.exam.id),
                        str(self.student.id))
        self.assertEqual(self.ds.get_remarks(sid, eid, st), {})
        self.assertIsNone(self.ds.get_fee_note(sid, st))


class EntryTests(SourceCase):
    def test_approved_and_locked_are_scored(self):
        self.mark(self.maths, 70, "approved")
        self.mark(self.science, 55, "locked")
        e = self.entries()
        self.assertEqual(e["Mathematics"].score, Decimal("70"))
        self.assertEqual(e["Mathematics"].status, MarkStatus.SCORED)
        self.assertEqual(e["Science"].score, Decimal("55"))
        self.assertEqual(e["Science"].max_mark, Decimal("100"))

    def test_draft_and_submitted_are_pending_never_zero(self):
        self.mark(self.maths, 70, "draft")
        self.mark(self.science, 55, "submitted")
        for entry in self.entries().values():
            self.assertIsNone(entry.score)
            self.assertEqual(entry.status, MarkStatus.MISSING)

    def test_other_assessment_types_are_not_mixed_in(self):
        self.mark(self.maths, 40, "approved", kind="opener")
        self.mark(self.maths, 80, "approved", kind="end")
        self.assertEqual(self.entries()["Mathematics"].score, Decimal("80"))

    def test_paper_weights_become_components(self):
        SubjectPaper.objects.create(subject=self.maths, paper_number=1, weight=60)
        SubjectPaper.objects.create(subject=self.maths, paper_number=2, weight=40)
        self.mark(self.maths, 80, "approved", paper=1)
        self.mark(self.maths, 70, "approved", paper=2)
        entry = self.entries()["Mathematics"]
        self.assertIsNone(entry.score)
        self.assertEqual(
            [(c.name, c.weight, c.score) for c in entry.components],
            [("Paper 1", Decimal("60"), Decimal("80")),
             ("Paper 2", Decimal("40"), Decimal("70"))])
        self.assertTrue(all(c.status == MarkStatus.SCORED
                            for c in entry.components))

    def test_missing_or_unapproved_paper_stays_missing(self):
        SubjectPaper.objects.create(subject=self.maths, paper_number=1, weight=60)
        SubjectPaper.objects.create(subject=self.maths, paper_number=2, weight=40)
        self.mark(self.maths, 80, "approved", paper=1)
        c1, c2 = self.entries()["Mathematics"].components
        self.assertEqual(c1.status, MarkStatus.SCORED)
        self.assertEqual((c2.score, c2.status), (None, MarkStatus.MISSING))
        self.mark(self.maths, 70, "draft", paper=2)
        c2 = self.entries()["Mathematics"].components[1]
        self.assertEqual((c2.score, c2.status), (None, MarkStatus.MISSING))

    def test_stream_subject_with_no_marks_shows_as_pending(self):
        user = get_user_model().objects.create_user(
            "t1", first_name="Jane", last_name="Doe", password="x")
        teacher = TeacherProfile.objects.create(user=user, school=self.school)
        TeacherAssignment.objects.create(
            teacher=teacher, school=self.school, subject=self.science,
            stream=self.stream)
        self.mark(self.maths, 70, "approved")
        e = self.entries()
        self.assertEqual(set(e), {"Mathematics", "Science"})
        self.assertEqual(e["Science"].status, MarkStatus.MISSING)
        self.assertIsNone(e["Science"].score)
        self.assertEqual(e["Science"].teacher, "Jane Doe")

    def test_student_with_no_marks_has_no_entries(self):
        self.assertEqual(self.entries(), {})


class AttendanceTests(SourceCase):
    def att(self, day, status="present", student=None):
        return AttendanceRecord.objects.create(
            student=student or self.student, date=day, status=status)

    def call(self):
        return self.ds.get_attendance(
            str(self.school.id), str(self.exam.id), str(self.student.id))

    def test_none_when_nothing_recorded(self):
        self.assertIsNone(self.call())

    def test_counts_and_open_days(self):
        other = Student.objects.create(
            school=self.school, first_name="Brian", last_name="K",
            admission_number="A-2")
        self.att(date(2026, 9, 1), "present")
        self.att(date(2026, 9, 2), "late")
        self.att(date(2026, 9, 3), "absent")
        self.att(date(2026, 9, 4), "excused")
        self.att(date(2026, 9, 7), "present", other)  # open day, no record for her
        self.att(date(2026, 7, 1), "present")         # outside Term 3
        a = self.call()
        self.assertEqual(a.days_open, 5)
        self.assertEqual((a.days_present, a.days_late, a.days_absent), (2, 1, 1))


class IsolationTests(SourceCase):
    def test_other_school_cannot_read_anything(self):
        other_id = str(self.other.id)
        eid, st = str(self.exam.id), str(self.student.id)
        for call in (
            lambda: self.ds.get_exam(other_id, eid),
            lambda: self.ds.get_student(other_id, st),
            lambda: self.ds.get_entries(other_id, eid, st),
            lambda: self.ds.get_remarks(other_id, eid, st),
            lambda: self.ds.get_fee_note(other_id, st),
            lambda: self.ds.get_attendance(other_id, eid, st),
        ):
            with self.assertRaises(NotFound):
                call()
        self.assertEqual(self.ds.list_students(other_id), [])
        self.assertEqual(self.ds.list_exams(other_id), [])

    def test_unknown_or_malformed_ids_are_not_found(self):
        with self.assertRaises(NotFound):
            self.ds.get_school("abc")
        with self.assertRaises(NotFound):
            self.ds.get_school("999999")
        with self.assertRaises(NotFound):
            self.ds.get_exam(str(self.school.id), "abc")


from schools.models import ReportRemark  # noqa: E402
from api.report_source import DjangoRemarkStore  # noqa: E402


class RemarkTests(SourceCase):
    def setUp(self):
        super().setUp()
        self.store = DjangoRemarkStore()
        self.ids = (str(self.school.id), str(self.exam.id), str(self.student.id))

    def remarks(self):
        return self.ds.get_remarks(*self.ids)

    def test_nothing_stored_means_no_remarks(self):
        self.assertEqual(self.remarks(), {})

    def test_approved_text_is_returned_by_field(self):
        self.store.set_remark(self.exam.id, self.student.id, "class_teacher", "Good work.")
        self.store.set_remark(str(self.exam.id), str(self.student.id), "principal", "Keep going.")
        self.assertEqual(self.remarks(), {
            "class_teacher": "Good work.", "principal": "Keep going."})

    def test_setting_again_replaces_and_never_duplicates(self):
        self.store.set_remark(self.exam.id, self.student.id, "principal", "First.")
        self.store.set_remark(self.exam.id, self.student.id, "principal", "Second.")
        self.assertEqual(ReportRemark.objects.count(), 1)
        self.assertEqual(self.remarks(), {"principal": "Second."})

    def test_clear_removes_only_that_field(self):
        self.store.set_remark(self.exam.id, self.student.id, "class_teacher", "A.")
        self.store.set_remark(self.exam.id, self.student.id, "principal", "B.")
        self.store.clear_remark(self.exam.id, self.student.id, "principal")
        self.assertEqual(self.remarks(), {"class_teacher": "A."})

    def test_other_school_cannot_read_remarks(self):
        self.store.set_remark(self.exam.id, self.student.id, "principal", "Private.")
        with self.assertRaises(NotFound):
            self.ds.get_remarks(str(self.other.id), self.ids[1], self.ids[2])

    def test_remark_for_a_student_of_another_school_is_refused(self):
        outsider = Student.objects.create(
            school=self.other, first_name="X", last_name="Y", admission_number="B-1")
        with self.assertRaises(NotFound):
            self.store.set_remark(self.exam.id, outsider.id, "principal", "No.")
        self.assertEqual(ReportRemark.objects.count(), 0)

    def test_unknown_field_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.set_remark(self.exam.id, self.student.id, "caretaker", "No.")


from schools.models import ReportComment  # noqa: E402
from api.report_source import DjangoCommentStore  # noqa: E402
from marian_reports.comments import CommentService  # noqa: E402
from marian_reports.domain import User  # noqa: E402


def comment_row(school, exam, student, cid="c1", text="Good work.", status="draft"):
    return {"id": cid, "school_id": str(school.id), "exam_id": str(exam.id),
            "student_id": str(student.id), "class_name": "Form 3",
            "field": "class_teacher", "text": text, "status": status,
            "source": "teacher", "edited": False, "approved_by": "",
            "created_by": "7", "at": 1234.5}


class CommentStoreTests(SourceCase):
    def store(self, school=None):
        return DjangoCommentStore((school or self.school).id)

    def row(self, **kw):
        return comment_row(self.school, self.exam, self.student, **kw)

    def test_save_then_load_round_trips(self):
        row = self.row()
        self.store().save(row)
        self.assertEqual(self.store().load(), {"c1": row})

    def test_saving_again_updates_and_never_duplicates(self):
        self.store().save(self.row())
        self.store().save(self.row(text="Better.", status="approved"))
        self.assertEqual(ReportComment.objects.count(), 1)
        loaded = self.store().load()["c1"]
        self.assertEqual((loaded["text"], loaded["status"]), ("Better.", "approved"))

    def test_delete_removes_only_that_row(self):
        self.store().save(self.row(cid="c1"))
        self.store().save(self.row(cid="c2"))
        self.store().delete("c1")
        self.assertEqual(list(self.store().load()), ["c2"])

    def test_other_school_sees_nothing(self):
        self.store().save(self.row())
        self.assertEqual(self.store(self.other).load(), {})

    def test_other_school_cannot_save_or_delete_our_rows(self):
        self.store().save(self.row())
        with self.assertRaises(NotFound):
            self.store(self.other).save(self.row())
        self.store(self.other).delete("c1")
        self.assertEqual(ReportComment.objects.count(), 1)

    def test_student_of_another_school_is_refused(self):
        outsider = Student.objects.create(
            school=self.other, first_name="X", last_name="Y", admission_number="B-1")
        bad = comment_row(self.school, self.exam, outsider)
        with self.assertRaises(NotFound):
            self.store().save(bad)
        self.assertEqual(ReportComment.objects.count(), 0)


class CommentFlowTests(SourceCase):
    def service(self):
        class Svc:
            def authorize_class(self, user, class_name):
                return None

        class Audit:
            def record(self, *args):
                pass

        remarks = DjangoRemarkStore()
        return CommentService(
            self.ds, Svc(), Audit(), remarks.set_remark, remarks.clear_remark,
            store=DjangoCommentStore(self.school.id))

    def teacher(self):
        return User(id="7", school_id=str(self.school.id), role="teacher",
                    class_names=("Form 3",))

    def test_draft_approve_print_across_service_instances(self):
        user, exam, stu = self.teacher(), str(self.exam.id), str(self.student.id)
        ids = (str(self.school.id), exam, stu)
        row = self.service().draft(user, exam, stu, "class_teacher", text="Good work.")
        self.assertEqual(self.ds.get_remarks(*ids), {})  # a draft never prints
        self.service().approve(user, row["id"])  # a fresh instance, as a new request
        self.assertEqual(self.ds.get_remarks(*ids), {"class_teacher": "Good work."})
        self.service().edit(user, row["id"], "Better.")
        self.assertEqual(self.ds.get_remarks(*ids), {})  # edit pulls it back to draft
        self.assertEqual(ReportComment.objects.get(id=row["id"]).status, "draft")

    def test_listing_in_a_new_instance_sees_the_saved_draft(self):
        user, exam, stu = self.teacher(), str(self.exam.id), str(self.student.id)
        row = self.service().draft(user, exam, stu, "class_teacher", text="Hello.")
        listed = self.service().listing(user, exam, "Form 3")
        self.assertEqual([r["id"] for r in listed], [row["id"]])
