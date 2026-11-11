from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from schools.models import (
    AcademicYear, ClassLevel, Curriculum, Enrollment, Exam, MarkAuditLog,
    Performance, School, Stream, Student, Subject, SubjectPaper,
    SubjectRegistration, TeacherAssignment, TeacherProfile, Term,
)


class PerformanceBatchTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Batch Marks", code="BATCH")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        self.term = Term.objects.create(
            academic_year=self.year, name="Term 1", start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 30),
        )
        curriculum = Curriculum.objects.create(name="CBC", code="BATCH-CBC")
        self.level = ClassLevel.objects.create(
            curriculum=curriculum, name="Grade 8", level_number=8,
        )
        self.east = Stream.objects.create(
            school=self.school, class_level=self.level, name="East",
        )
        self.west = Stream.objects.create(
            school=self.school, class_level=self.level, name="West",
        )
        self.subject = Subject.objects.create(
            school=self.school, name="Mathematics", code="MATH",
        )
        for number, weight in ((1, 40), (2, 40), (3, 20)):
            SubjectPaper.objects.create(
                subject=self.subject, paper_number=number,
                weight=Decimal(str(weight)), max_marks=Decimal("50"),
            )
        self.exam = Exam.objects.create(
            school=self.school, name="End Term", term=self.term,
            assessment_type="end", class_level=self.level,
        )
        self.teacher_user = User.objects.create_user("batchteacher", password="pass12345")
        teacher = TeacherProfile.objects.create(user=self.teacher_user, school=self.school)
        TeacherAssignment.objects.create(
            teacher=teacher, school=self.school, subject=self.subject, stream=self.east,
        )
        self.learners = []
        for number, stream in ((1, self.east), (2, self.east), (3, self.west)):
            student = Student.objects.create(
                school=self.school, first_name=f"Learner{number}", last_name="Test",
                admission_number=f"BM-{number}",
            )
            Enrollment.objects.create(
                student=student, academic_year=self.year, class_level=self.level,
                stream=stream,
            )
            SubjectRegistration.objects.create(
                student=student, academic_year=self.year, subject=self.subject,
                category="compulsory",
            )
            self.learners.append(student)
        self.client.force_authenticate(self.teacher_user)

    def batch(self, entries, **extra):
        return self.client.post("/api/performance/batch/", {
            "exam": self.exam.id,
            "subject": self.subject.id,
            "entries": entries,
            **extra,
        }, format="json")

    def test_batch_saves_aligned_papers_as_audited_drafts(self):
        response = self.batch([
            {"student": self.learners[0].id, "paper_number": 1, "marks": "40"},
            {"student": self.learners[0].id, "paper_number": 2, "marks": "35"},
            {"student": self.learners[0].id, "paper_number": 3, "marks": "45"},
            {"student": self.learners[1].id, "paper_number": 1, "marks": "30"},
        ])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {
            "exam": self.exam.id, "subject": self.subject.id,
            "saved": 4, "created": 4, "updated": 0, "deleted": 0,
        })
        marks = list(Performance.objects.order_by("student_id", "paper_number"))
        self.assertEqual(len(marks), 4)
        self.assertTrue(all(mark.status == "draft" for mark in marks))
        self.assertEqual(MarkAuditLog.objects.filter(action="created").count(), 4)
        self.assertTrue(all(mark.performance_id for mark in MarkAuditLog.objects.filter(action="created")))

    def test_batch_edits_only_existing_drafts(self):
        original = Performance.objects.create(
            student=self.learners[0], subject=self.subject, academic_year=self.year,
            term=self.term, assessment_type="end", paper_number=1, marks=20,
            status="draft",
        )
        response = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "41.5",
        }])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["updated"], 1)
        original.refresh_from_db()
        self.assertEqual(original.marks, Decimal("41.50"))
        self.assertEqual(original.status, "draft")
        self.assertTrue(MarkAuditLog.objects.filter(
            performance=original, action="edited",
            details__from__marks="20.00", details__to__marks="41.50",
        ).exists())

    def test_batch_accepts_zero_and_explicit_non_scored_dispositions(self):
        response = self.batch([
            {"student": self.learners[0].id, "paper_number": 1,
             "marks": "0", "mark_status": "scored"},
            {"student": self.learners[0].id, "paper_number": 2,
             "marks": None, "mark_status": "absent"},
            {"student": self.learners[1].id, "paper_number": 1,
             "marks": None, "mark_status": "exempted"},
            {"student": self.learners[1].id, "paper_number": 2,
             "marks": None, "mark_status": "not_assessed"},
            {"student": self.learners[1].id, "paper_number": 3,
             "marks": None, "mark_status": "pending"},
        ])
        self.assertEqual(response.status_code, 200, response.content)
        marks = {(row.student_id, row.paper_number): row
                 for row in Performance.objects.all()}
        self.assertEqual(marks[(self.learners[0].id, 1)].marks, Decimal("0.00"))
        self.assertEqual(marks[(self.learners[0].id, 1)].mark_status, "scored")
        self.assertEqual(marks[(self.learners[0].id, 2)].marks, None)
        self.assertEqual(marks[(self.learners[0].id, 2)].mark_status, "absent")
        self.assertEqual(marks[(self.learners[1].id, 1)].mark_status, "exempted")
        self.assertEqual(marks[(self.learners[1].id, 2)].mark_status, "not_assessed")
        self.assertEqual(marks[(self.learners[1].id, 3)].mark_status, "pending")

    def test_batch_submit_submits_resolved_rows_and_leaves_pending_draft(self):
        saved = self.batch([
            {"student": self.learners[0].id, "paper_number": 1,
             "marks": "0", "mark_status": "scored"},
            {"student": self.learners[0].id, "paper_number": 2,
             "marks": None, "mark_status": "absent"},
            {"student": self.learners[1].id, "paper_number": 1,
             "marks": None, "mark_status": "exempted"},
            {"student": self.learners[1].id, "paper_number": 2,
             "marks": None, "mark_status": "not_assessed"},
            {"student": self.learners[1].id, "paper_number": 3,
             "marks": None, "mark_status": "pending"},
        ])
        self.assertEqual(saved.status_code, 200, saved.content)
        response = self.client.post("/api/performance/batch/submit/", {
            "exam": self.exam.id, "subject": self.subject.id, "stream": self.east.id,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["submitted"], response.json()["pending"]), (4, 1))
        submitted = Performance.objects.exclude(mark_status="pending")
        self.assertTrue(all(row.status == "submitted" for row in submitted))
        self.assertEqual(Performance.objects.get(mark_status="pending").status, "draft")
        logs = MarkAuditLog.objects.filter(action="submit")
        self.assertEqual(logs.count(), 4)
        self.assertEqual(len(set(logs.values_list("details__operation_id", flat=True))), 1)
        self.assertTrue(all(log.performance_id for log in logs))

    def test_batch_rejects_numeric_marks_for_non_scored_status(self):
        response = self.batch([{
            "student": self.learners[0].id, "paper_number": 1,
            "marks": "0", "mark_status": "absent",
        }])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Performance.objects.count(), 0)

    def test_performance_list_filters_selected_class_and_stream(self):
        for student in (self.learners[0], self.learners[1], self.learners[2]):
            Performance.objects.create(
                student=student, subject=self.subject, academic_year=self.year,
                term=self.term, assessment_type="end", paper_number=1,
                marks=Decimal("30"),
            )
        response = self.client.get(
            "/api/performance/",
            {"term": self.term.id, "academic_year": self.year.id,
             "subject": self.subject.id, "assessment_type": "end",
             "class_level": self.level.id, "stream": self.east.id},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual({row["student"] for row in response.json()["results"]},
                         {self.learners[0].id, self.learners[1].id})

    def test_performance_list_rejects_invalid_filters(self):
        response = self.client.get("/api/performance/?term=oops")
        self.assertEqual(response.status_code, 400)

    def test_teacher_registration_lookup_is_limited_to_assigned_streams(self):
        response = self.client.get(
            "/api/subject-registrations/",
            {"academic_year": self.year.id, "subject": self.subject.id},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual(
            {row["student"] for row in response.json()["results"]},
            {self.learners[0].id, self.learners[1].id},
        )

    def test_invalid_cell_rejects_entire_batch_without_partial_writes(self):
        response = self.batch([
            {"student": self.learners[0].id, "paper_number": 1, "marks": "40"},
            {"student": self.learners[1].id, "paper_number": 1, "marks": "51"},
        ])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Performance.objects.count(), 0)
        self.assertIn("errors", response.json())

    def test_unregistered_or_other_stream_learner_is_rejected_atomically(self):
        SubjectRegistration.objects.filter(student=self.learners[1]).delete()
        response = self.batch([
            {"student": self.learners[0].id, "paper_number": 1, "marks": "40"},
            {"student": self.learners[1].id, "paper_number": 1, "marks": "30"},
        ])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Performance.objects.count(), 0)
        assigned_stream_response = self.batch([{
            "student": self.learners[2].id, "paper_number": 1, "marks": "30",
        }])
        self.assertEqual(assigned_stream_response.status_code, 403)
        self.assertEqual(Performance.objects.count(), 0)

    def test_published_marks_cannot_be_edited(self):
        mark = Performance.objects.create(
            student=self.learners[0], subject=self.subject, academic_year=self.year,
            term=self.term, assessment_type="end", paper_number=1, marks=20,
            status="submitted",
        )
        response = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "40",
        }])
        self.assertEqual(response.status_code, 409)
        mark.refresh_from_db()
        self.assertEqual(mark.marks, Decimal("20.00"))
        self.assertEqual(mark.status, "submitted")

    def test_published_exam_rejects_new_batch(self):
        self.exam.status = "published"
        self.exam.save(update_fields=["status"])
        response = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "40",
        }])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Performance.objects.count(), 0)

    def test_blank_cell_clears_saved_draft_and_keeps_audit_trail(self):
        mark = Performance.objects.create(
            student=self.learners[0], subject=self.subject, academic_year=self.year,
            term=self.term, assessment_type="end", paper_number=1, marks=20,
            status="draft",
        )
        response = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "",
        }])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["deleted"], 1)
        self.assertFalse(Performance.objects.filter(pk=mark.pk).exists())
        audit = MarkAuditLog.objects.get(action="deleted")
        self.assertIsNone(audit.performance_id)
        self.assertEqual(audit.details["mark_id"], mark.pk)

    def test_duplicate_entries_and_undefined_paper_are_rejected(self):
        duplicate = self.batch([
            {"student": self.learners[0].id, "paper_number": 1, "marks": "30"},
            {"student": self.learners[0].id, "paper_number": 1, "marks": "35"},
        ])
        undefined = self.batch([{
            "student": self.learners[0].id, "paper_number": 4, "marks": "30",
        }])
        invalid_id = self.batch([{
            "student": True, "paper_number": 1, "marks": "30",
        }])
        invalid_mark = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": True,
        }])
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(undefined.status_code, 400)
        self.assertEqual(invalid_id.status_code, 400)
        self.assertEqual(invalid_mark.status_code, 400)
        self.assertEqual(Performance.objects.count(), 0)

    def test_offline_operation_replay_is_idempotent_and_payload_bound(self):
        operation_id = str(uuid4())
        entries = [{"student": self.learners[0].id, "paper_number": 1, "marks": "42"}]
        first = self.batch(entries, offline_operation_id=operation_id)
        replay = self.batch(entries, offline_operation_id=operation_id)
        changed = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "43",
        }], offline_operation_id=operation_id)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(Performance.objects.get().marks, Decimal("42.00"))
        self.assertEqual(MarkAuditLog.objects.filter(action="created").count(), 1)

    def test_offline_expected_updated_at_rejects_stale_and_null_versions(self):
        mark = Performance.objects.create(
            student=self.learners[0], subject=self.subject, academic_year=self.year,
            term=self.term, assessment_type="end", paper_number=1, marks=20,
            status="draft",
        )
        stale = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "30",
            "expected_updated_at": "2000-01-01T00:00:00Z",
        }])
        absent = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "30",
            "expected_updated_at": None,
        }])
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(absent.status_code, 409)
        mark.refresh_from_db()
        self.assertEqual(mark.marks, Decimal("20.00"))
        current = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "30",
            "expected_updated_at": mark.updated_at.isoformat(),
        }])
        self.assertEqual(current.status_code, 200, current.content)
        mark.refresh_from_db()
        self.assertEqual(mark.marks, Decimal("30.00"))

    def test_offline_expected_null_allows_only_a_new_mark_and_uuid_is_validated(self):
        accepted = self.batch([{
            "student": self.learners[0].id, "paper_number": 1, "marks": "0",
            "expected_updated_at": None,
        }])
        bad_id = self.batch([{
            "student": self.learners[1].id, "paper_number": 1, "marks": "20",
        }], offline_operation_id="not-a-uuid")
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(bad_id.status_code, 400)
