import hashlib
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import LearningInvitation, LearningProfile
from schools.models import (
    GuardianProfile,
    School,
    SchoolAdminProfile,
    Student,
    StudentGuardian,
    TeacherProfile,
)

User = get_user_model()
from rest_framework.test import APITestCase
from learning.models import LearningAuditEvent, LearningInvitation

BULK = "/api/learning/v1/admin/invitations/bulk/"
SINGLE = "/api/learning/v1/admin/invitations/"


class BulkInvitationTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", code="NORTH")
        self.other_school = School.objects.create(name="South School", code="SOUTH")
        self.admin = User.objects.create_user("north_admin", password="SchoolAdmin!123")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school, is_deputy=False)
        self.deputy = User.objects.create_user("north_deputy", password="SchoolAdmin!123")
        SchoolAdminProfile.objects.create(user=self.deputy, school=self.school, is_deputy=True)
        self.teacher = User.objects.create_user("north_teacher", password="TeacherPass!123")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.other_student = self.make_student(self.other_school, "S-001", dob=date(2010, 3, 5))

    @staticmethod
    def make_student(school, admission, dob=None, status="active"):
        return Student.objects.create(
            school=school, first_name="Amina", last_name="Learner",
            admission_number=admission, date_of_birth=dob, status=status,
        )

    def adult(self, n):
        return self.make_student(self.school, f"A-{n:03d}", dob=date(2000, 1, 1))

    def bulk(self, ids, user=None):
        self.client.force_authenticate(user or self.admin)
        return self.client.post(BULK, {"student_ids": ids}, format="json")

    def test_issues_one_invitation_per_selected_student(self):
        students = [self.adult(i) for i in range(3)]
        r = self.bulk([s.pk for s in students])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["created"], 3)
        for item in r.data["results"]:
            self.assertEqual(item["status"], 201)
            self.assertTrue(item["result"]["claim_token"])
        self.assertEqual(LearningInvitation.objects.count(), 3)

    def test_each_student_is_judged_by_the_single_invite_rules(self):
        ok = self.adult(1)
        minor = self.make_student(self.school, "M-001", dob=date(2014, 6, 1))
        already = self.adult(2)
        self.client.force_authenticate(self.admin)
        first = self.client.post(SINGLE, {"student_id": already.pk}, format="json")
        self.assertEqual(first.status_code, 201)
        r = self.bulk([ok.pk, minor.pk, self.other_student.pk, already.pk, "abc"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["status"] for x in r.data["results"]], [201, 409, 404, 409, 400])
        self.assertEqual(r.data["created"], 1)
        self.assertFalse(LearningInvitation.objects.filter(student=minor).exists())

    def test_input_limits(self):
        self.assertEqual(self.bulk(list(range(1, 52))).status_code, 400)
        self.assertEqual(self.bulk([]).status_code, 400)
        self.assertEqual(self.bulk("5").status_code, 400)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(BULK, {}, format="json").status_code, 400)
        at_cap = self.bulk([900000 + i for i in range(50)])
        self.assertEqual(at_cap.status_code, 200)
        self.assertEqual(at_cap.data["created"], 0)

    def test_duplicate_ids_are_ignored(self):
        a = self.adult(1)
        r = self.bulk([a.pk, a.pk])
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["created"], 1)

    def test_only_full_school_admin_may_use_it(self):
        a = self.adult(1)
        self.assertEqual(self.bulk([a.pk], user=self.teacher).status_code, 403)
        self.assertEqual(self.bulk([a.pk], user=self.deputy).status_code, 403)
        self.client.force_authenticate(None)
        anon = self.client.post(BULK, {"student_ids": [a.pk]}, format="json")
        self.assertIn(anon.status_code, (401, 403))
        self.assertEqual(LearningInvitation.objects.count(), 0)

    def test_summary_audit_event_is_written(self):
        students = [self.adult(1), self.adult(2)]
        self.bulk([s.pk for s in students])
        events = LearningAuditEvent.objects.filter(action="school_invitations_bulk_issued")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().safe_details, {"requested": 2, "created": 2})
