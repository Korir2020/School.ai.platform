from rest_framework.test import APITestCase

from schools.models import (
    ExamResult, MarkAuditLog, Performance, Subject, TeacherAssignment,
    TeacherProfile,
)
from . import tests as base


class PublishFairnessTests(APITestCase):
    payload = base.MarksEntryTests.payload

    def setUp(self):
        base.ExamPublishTests.setUp(self)
        self.science = Subject.objects.create(
            school=self.school, name="Science", code="SC")
        TeacherAssignment.objects.create(
            teacher=TeacherProfile.objects.get(user=self.good),
            school=self.school, subject=self.science, stream=self.stream)
        self.s2 = base.ExamPublishTests.add_student(self, "S-2")

    def sci(self, student, marks):
        return Performance.objects.create(
            student=student, subject=self.science, academic_year=self.year,
            term=self.term, assessment_type="end", paper_number=1,
            marks=marks, status="approved")

    def test_partial_student_blocked_until_min_mark_given(self):
        for st in (self.student, self.s2):
            base.ExamPublishTests.mark(self, st, 1, 60)
        self.sci(self.student, 50)
        r = base.ExamPublishTests.publish(self, self.admin)
        self.assertEqual(r.status_code, 409)
        problem = r.json()["problems"][0]
        self.assertEqual(problem["admission_number"], "S-2")
        self.assertEqual(problem["missing_subjects"], ["Science"])
        self.assertEqual(ExamResult.objects.count(), 0)
        self.sci(self.s2, 1)
        ok = base.ExamPublishTests.publish(self, self.admin)
        self.assertEqual(ok.status_code, 200)
        res = ExamResult.objects.get(student=self.s2)
        self.assertEqual(res.subject_scores["Science"], "1.00")
        self.assertEqual(ExamResult.objects.count(), 2)

    def test_student_with_no_marks_is_excluded_and_reported(self):
        base.ExamPublishTests.mark(self, self.student, 1, 70)
        self.sci(self.student, 70)
        r = base.ExamPublishTests.publish(self, self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["not_ranked"][0]["admission_number"], "S-2")
        self.assertFalse(ExamResult.objects.filter(student=self.s2).exists())
        self.assertEqual(ExamResult.objects.get().class_rank, 1)
        log = MarkAuditLog.objects.get(action="publish")
        self.assertEqual(log.details["not_ranked"], ["S-2"])

    def test_ties_still_share_rank_1_1_3(self):
        s3 = base.ExamPublishTests.add_student(self, "S-3")
        for st, m in ((self.student, 70), (self.s2, 70), (s3, 60)):
            base.ExamPublishTests.mark(self, st, 1, m)
            self.sci(st, m)
        ok = base.ExamPublishTests.publish(self, self.admin)
        self.assertEqual(ok.status_code, 200)
        ranks = sorted(ExamResult.objects.values_list("class_rank", flat=True))
        self.assertEqual(ranks, [1, 1, 3])
