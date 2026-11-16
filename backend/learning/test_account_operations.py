from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from learning.models import (
    LearningAccountLifecycleRequest,
    LearningAuditEvent,
    LearningGuardianRelationship,
    LearningInvitation,
    LearningPath,
    LearningPathParticipation,
    LearningProfile,
)
from schools.models import (
    AcademicYear,
    ClassLevel,
    Curriculum,
    Enrollment,
    GuardianProfile,
    School,
    SchoolAdminProfile,
    Student,
    StudentGuardian,
    Stream,
    Subject,
    TeacherAssignment,
    TeacherProfile,
)

User = get_user_model()
BASE = "/api/learning/v1/"
CLAIM_URL = f"{BASE}invitations/claim/"


class Activity11AccountOperationTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Activity 11 School", code="A11")
        self.other_school = School.objects.create(name="Other Activity 11", code="OA11")
        self.admin = User.objects.create_user("a11_admin", password="SafeAdmin!123")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school, is_deputy=False)
        self.other_admin = User.objects.create_user("a11_other_admin", password="OtherAdmin!123")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=self.other_school, is_deputy=False)
        self.guardian_user = User.objects.create_user("a11_guardian", password="Guardian!123")
        self.guardian = GuardianProfile.objects.create(user=self.guardian_user, school=self.school)
        self.student = Student.objects.create(
            school=self.school, first_name="Amani", last_name="Learner",
            admission_number="A11-001", date_of_birth=date(2012, 1, 1),
        )
        StudentGuardian.objects.create(student=self.student, guardian=self.guardian)
        self.learner = User.objects.create_user("a11_learner", password="Learner!123")
        self.profile = LearningProfile.objects.create(
            user=self.learner, account_kind="school_student", school=self.school,
            student=self.student, age_band="10_17", consent_state="verified",
        )

    def test_capability_discovery_is_truthful_and_provider_flows_are_all_disabled(self):
        response = self.client.get(f"{BASE}accounts/capabilities/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["minimum_independent_age"], 10)
        self.assertFalse(payload["provider_configured"])
        self.assertFalse(payload["provider_ready"])
        self.assertFalse(any(payload["capabilities"].values()))
        self.assertFalse(payload["deletion_execution_available"])
        self.assertFalse(payload["retention_policy_configured"])

    def test_independent_registration_returns_unavailable_without_creating_or_verifying_accounts(self):
        before_users = User.objects.count()
        response = self.client.post(f"{BASE}accounts/register/", {
            "username": "not_created", "email": "nobody@example.test", "date_of_birth": "2000-01-01",
        }, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["registration_created"])
        self.assertFalse(User.objects.filter(username="not_created").exists())
        self.assertEqual(User.objects.count(), before_users)
        self.assertFalse(LearningProfile.objects.filter(account_kind="public_learner").exists())

    def test_linked_guardian_can_withdraw_school_minor_consent_and_learning_is_blocked(self):
        self.client.force_authenticate(self.guardian_user)
        response = self.client.post(f"{BASE}guardians/learners/{self.profile.pk}/consent/withdraw/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.consent_state, "withdrawn")
        self.assertTrue(LearningAuditEvent.objects.filter(
            actor=self.guardian_user, action="guardian_consent_withdrawn", target_id=str(self.profile.pk),
        ).exists())
        self.client.force_authenticate(self.learner)
        self.assertEqual(self.client.get(f"{BASE}me/").status_code, 403)

    def test_guardian_summary_hides_progress_for_withdrawn_consent(self):
        path = LearningPath.objects.create(scope="school", school=self.school, title="Existing progress")
        LearningPathParticipation.objects.create(
            profile=self.profile, path=path, path_version=1, last_activity_at=timezone.now(),
        )
        self.profile.consent_state = "withdrawn"
        self.profile.save(update_fields=["consent_state"])
        self.client.force_authenticate(self.guardian_user)
        response = self.client.get(f"{BASE}guardians/learners/")
        self.assertEqual(response.status_code, 200, response.content)
        learner = response.json()["results"][0]
        self.assertEqual(learner["consent_state"], "withdrawn")
        self.assertEqual(learner["participation_count"], 0)
        self.assertIsNone(learner["last_activity_at"])

    def test_unlinked_guardian_cannot_read_or_withdraw_a_learner(self):
        other_guardian = User.objects.create_user("a11_unlinked_guardian")
        GuardianProfile.objects.create(user=other_guardian, school=self.school)
        self.client.force_authenticate(other_guardian)
        self.assertEqual(self.client.get(f"{BASE}guardians/learners/").json()["results"], [])
        response = self.client.post(f"{BASE}guardians/learners/{self.profile.pk}/consent/withdraw/", {}, format="json")
        self.assertEqual(response.status_code, 404)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.consent_state, "verified")

    def test_guardian_summary_contains_only_linked_learner_and_is_audited(self):
        second_student = Student.objects.create(
            school=self.school, first_name="Other", last_name="Learner",
            admission_number="A11-002", date_of_birth=date(2012, 5, 1),
        )
        other_user = User.objects.create_user("a11_other_learner")
        LearningProfile.objects.create(
            user=other_user, account_kind="school_student", school=self.school,
            student=second_student, age_band="10_17", consent_state="verified",
        )
        self.client.force_authenticate(self.guardian_user)
        response = self.client.get(f"{BASE}guardians/learners/")
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["results"]
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["profile_id"], self.profile.pk)
        self.assertEqual(payload[0]["learner_name"], "Amani Learner")
        self.assertNotIn("password", payload[0])
        self.assertTrue(LearningAuditEvent.objects.filter(
            actor=self.guardian_user, action="guardian_learning_summary_read",
        ).exists())

    def test_deletion_request_is_non_destructive_access_restricting_and_cancellable(self):
        self.client.force_authenticate(self.learner)
        response = self.client.post(f"{BASE}account/lifecycle-requests/", {"request_type": "deletion"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        request_id = response.json()["id"]
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.account_status, "pending_deletion")
        self.assertTrue(User.objects.filter(pk=self.learner.pk).exists())
        self.assertEqual(self.client.get(f"{BASE}me/").status_code, 403)
        self.assertEqual(LearningAccountLifecycleRequest.objects.get(pk=request_id).status, "pending")
        history = self.client.get(f"{BASE}account/lifecycle-requests/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["results"][0]["id"], request_id)
        cancelled = self.client.post(f"{BASE}account/lifecycle-requests/{request_id}/cancel/", {}, format="json")
        self.assertEqual(cancelled.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.account_status, "active")
        self.assertEqual(LearningAccountLifecycleRequest.objects.get(pk=request_id).status, "cancelled")
        self.assertTrue(LearningAuditEvent.objects.filter(action="account_deletion_requested").exists())
        self.assertTrue(LearningAuditEvent.objects.filter(action="account_lifecycle_request_cancelled").exists())

    def test_verified_guardian_may_request_child_deletion_but_not_delete_the_user(self):
        self.client.force_authenticate(self.guardian_user)
        response = self.client.post(f"{BASE}account/lifecycle-requests/", {
            "request_type": "deletion", "profile_id": self.profile.pk,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        request_row = LearningAccountLifecycleRequest.objects.get(pk=response.json()["id"])
        self.assertEqual(request_row.reason_code, "guardian_request")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.account_status, "pending_deletion")
        self.assertTrue(User.objects.filter(pk=self.learner.pk).exists())
        self.assertFalse(hasattr(response.json(), "password"))

    def test_school_admin_can_suspend_only_own_school_learning_accounts(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"{BASE}admin/learning-accounts/{self.profile.pk}/state/", {
            "account_status": "suspended",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.account_status, "suspended")
        self.assertTrue(LearningAuditEvent.objects.filter(action="school_learner_account_state_changed").exists())
        self.client.force_authenticate(self.learner)
        self.assertEqual(self.client.get(f"{BASE}me/").status_code, 403)
        self.client.force_authenticate(self.other_admin)
        cross_school = self.client.post(f"{BASE}admin/learning-accounts/{self.profile.pk}/state/", {
            "account_status": "active",
        }, format="json")
        self.assertEqual(cross_school.status_code, 404)

    def test_school_admin_account_list_is_minimum_necessary_and_tenant_scoped(self):
        other_student = Student.objects.create(
            school=self.other_school, first_name="Other", last_name="School",
            admission_number="O-A11-LIST", date_of_birth=date(2012, 2, 1),
        )
        other_learner = User.objects.create_user("a11_other_list_learner", password="NeverExpose!123")
        LearningProfile.objects.create(
            user=other_learner, account_kind="school_student", school=self.other_school,
            student=other_student, age_band="10_17", consent_state="verified",
        )
        public_learner = User.objects.create_user("a11_public_list_learner", password="AlsoNeverExpose!123")
        LearningProfile.objects.create(
            user=public_learner, account_kind="public_learner", age_band="adult",
            consent_state="not_required",
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"{BASE}admin/learning-accounts/")
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 1)
        learner = payload["results"][0]
        self.assertEqual(learner["profile_id"], self.profile.pk)
        self.assertEqual(learner["student_name"], "Amani Learner")
        self.assertNotIn("password", learner)
        self.assertNotIn("date_of_birth", learner)
        self.assertNotIn("admission_number", learner)
        self.assertTrue(LearningAuditEvent.objects.filter(
            actor=self.admin, action="school_learning_accounts_list_read",
        ).exists())
        self.client.force_authenticate(self.other_admin)
        other_response = self.client.get(f"{BASE}admin/learning-accounts/")
        self.assertEqual(other_response.status_code, 200, other_response.content)
        self.assertEqual([row["profile_id"] for row in other_response.json()["results"]], [
            LearningProfile.objects.get(user=other_learner).pk,
        ])
        self.client.force_authenticate(self.guardian_user)
        self.assertEqual(self.client.get(f"{BASE}admin/learning-accounts/").status_code, 403)

    def test_school_summary_is_aggregate_and_excludes_public_and_other_schools(self):
        other_student = Student.objects.create(
            school=self.other_school, first_name="Other", last_name="Student",
            admission_number="O-A11-1", date_of_birth=date(2010, 1, 1),
        )
        other_user = User.objects.create_user("other_school_learner")
        LearningProfile.objects.create(
            user=other_user, account_kind="school_student", school=self.other_school,
            student=other_student, age_band="10_17", consent_state="verified",
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"{BASE}admin/learning-summary/")
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["learner_count"], 1)
        self.assertEqual(payload["active_account_count"], 1)
        self.assertNotIn("students", payload)
        self.assertNotIn("public", payload)
        self.assertTrue(LearningAuditEvent.objects.filter(action="school_learning_aggregate_read").exists())
        self.client.force_authenticate(self.other_admin)
        other_payload = self.client.get(f"{BASE}admin/learning-summary/").json()
        self.assertEqual(other_payload["learner_count"], 1)

    def test_invitation_resend_stays_disabled_and_preserves_one_time_token(self):
        adult_student = Student.objects.create(
            school=self.school, first_name="Adult", last_name="Learner",
            admission_number="A11-ADULT", date_of_birth=date(1990, 1, 1),
        )
        self.client.force_authenticate(self.admin)
        created = self.client.post(f"{BASE}admin/invitations/", {"student_id": adult_student.pk}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        raw_token = created.json()["claim_token"]
        self.assertEqual(created.json()["delivery_status"], "manual_handoff_required")
        invitation_id = created.json()["id"]
        from learning.models import LearningInvitation
        invitation = LearningInvitation.objects.get(pk=invitation_id)
        token_hash = invitation.token_hash
        resent = self.client.post(f"{BASE}admin/invitations/{invitation_id}/resend/", {}, format="json")
        self.assertEqual(resent.status_code, 503)
        self.assertEqual(resent.json()["delivery_status"], "manual_handoff_required")
        invitation.refresh_from_db()
        self.assertEqual(invitation.token_hash, token_hash)
        self.assertNotIn(raw_token, invitation.token_hash)
        self.assertTrue(LearningAuditEvent.objects.filter(action="invitation_delivery_unavailable").exists())
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save(update_fields=["expires_at"])
        expired_resend = self.client.post(f"{BASE}admin/invitations/{invitation_id}/resend/", {}, format="json")
        self.assertEqual(expired_resend.status_code, 409)
        self.assertNotIn("claim_token", expired_resend.json())

    def test_school_invitation_reads_are_audited_and_candidate_data_is_minimal_and_scoped(self):
        candidate = Student.objects.create(
            school=self.school, first_name="Available", last_name="Learner",
            admission_number="A11-CANDIDATE", date_of_birth=date(1990, 1, 1),
        )
        blocked_minor = Student.objects.create(
            school=self.school, first_name="Blocked", last_name="Learner",
            admission_number="A11-BLOCKED", date_of_birth=date(2012, 1, 1),
        )
        foreign_candidate = Student.objects.create(
            school=self.other_school, first_name="Foreign", last_name="Learner",
            admission_number="OA11-CANDIDATE", date_of_birth=date(1990, 1, 1),
        )
        self.client.force_authenticate(self.admin)

        invitation_list = self.client.get(f"{BASE}admin/invitations/")
        self.assertEqual(invitation_list.status_code, 200, invitation_list.content)
        self.assertTrue(LearningAuditEvent.objects.filter(
            actor=self.admin, action="school_invitation_list_read",
            target_id=str(self.school.pk),
        ).exists())

        candidates = self.client.get(f"{BASE}admin/invitation-candidates/")
        self.assertEqual(candidates.status_code, 200, candidates.content)
        rows = candidates.json()["results"]
        self.assertEqual({row["student_id"] for row in rows}, {candidate.pk, blocked_minor.pk})
        self.assertNotIn(foreign_candidate.pk, [row["student_id"] for row in rows])
        candidate_rows = {row["student_id"]: row for row in rows}
        self.assertEqual(candidate_rows[candidate.pk]["age_band"], "adult")
        self.assertFalse(candidate_rows[candidate.pk]["guardian_required"])
        self.assertFalse(candidate_rows[blocked_minor.pk]["guardian_available"])
        self.assertTrue(candidate_rows[blocked_minor.pk]["guardian_required"])
        for row in rows:
            self.assertNotIn("date_of_birth", row)
        self.assertTrue(LearningAuditEvent.objects.filter(
            actor=self.admin, action="school_invitation_candidates_read",
        ).exists())

    def test_guardian_pending_invitation_list_is_link_scoped_audited_and_approvable(self):
        pending_student = Student.objects.create(
            school=self.school, first_name="Pending", last_name="Learner",
            admission_number="A11-PENDING", date_of_birth=date(2012, 1, 1),
        )
        StudentGuardian.objects.create(student=pending_student, guardian=self.guardian)
        self.client.force_authenticate(self.admin)
        issued = self.client.post(f"{BASE}admin/invitations/", {"student_id": pending_student.pk}, format="json")
        self.assertEqual(issued.status_code, 201, issued.content)
        invitation_id = issued.json()["id"]

        unlinked_user = User.objects.create_user("a11_unlinked_pending_guardian")
        GuardianProfile.objects.create(user=unlinked_user, school=self.school)
        self.client.force_authenticate(unlinked_user)
        unlinked = self.client.get(f"{BASE}guardians/invitations/")
        self.assertEqual(unlinked.status_code, 200, unlinked.content)
        self.assertEqual(unlinked.json()["results"], [])

        self.client.force_authenticate(self.guardian_user)
        pending = self.client.get(f"{BASE}guardians/invitations/")
        self.assertEqual(pending.status_code, 200, pending.content)
        self.assertEqual(len(pending.json()["results"]), 1)
        self.assertEqual(pending.json()["results"][0]["id"], invitation_id)
        self.assertEqual(pending.json()["results"][0]["student_name"], "Pending Learner")
        self.assertNotIn("claim_token", pending.json()["results"][0])
        self.assertNotIn("date_of_birth", pending.json()["results"][0])
        self.assertTrue(LearningAuditEvent.objects.filter(
            actor=self.guardian_user, action="guardian_pending_invitation_list_read",
        ).exists())

        approved = self.client.post(f"{BASE}invitations/{invitation_id}/guardian-approval/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(self.client.get(f"{BASE}guardians/invitations/").json()["results"], [])

    def test_expired_unclaimed_invitation_is_retired_before_safe_reissue(self):
        adult_student = Student.objects.create(
            school=self.school, first_name="Adult", last_name="Learner",
            admission_number="A11-REISSUE", date_of_birth=date(1990, 1, 1),
        )
        self.client.force_authenticate(self.admin)
        first = self.client.post(f"{BASE}admin/invitations/", {"student_id": adult_student.pk}, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        old_invitation = LearningInvitation.objects.get(pk=first.json()["id"])
        old_token = first.json()["claim_token"]
        old_hash = old_invitation.token_hash
        old_invitation.expires_at = timezone.now() - timedelta(seconds=1)
        old_invitation.save(update_fields=["expires_at"])

        second = self.client.post(f"{BASE}admin/invitations/", {"student_id": adult_student.pk}, format="json")
        self.assertEqual(second.status_code, 201, second.content)
        self.assertNotEqual(second.json()["id"], old_invitation.pk)
        self.assertNotEqual(second.json()["claim_token"], old_token)
        old_invitation.refresh_from_db()
        self.assertIsNotNone(old_invitation.revoked_at)
        new_invitation = LearningInvitation.objects.get(pk=second.json()["id"])
        self.assertNotEqual(new_invitation.token_hash, old_hash)
        self.assertTrue(LearningAuditEvent.objects.filter(
            actor=self.admin, action="expired_invitation_retired_for_reissue",
            safe_details__invitation_id=old_invitation.pk,
        ).exists())
        old_claim = self.client.post(CLAIM_URL, {
            "token": old_token, "username": "old_invite_reuse", "password": "N4vigator!Learning2026",
        }, format="json")
        self.assertEqual(old_claim.status_code, 400)
        self.assertFalse(User.objects.filter(username="old_invite_reuse").exists())

    def test_assigned_teacher_gets_minimal_progress_only_for_current_assigned_learners(self):
        curriculum = Curriculum.objects.create(name="CBC", code="a11-cbc")
        level = ClassLevel.objects.create(curriculum=curriculum, name="Grade 7", level_number=7)
        stream = Stream.objects.create(school=self.school, class_level=level, name="Blue")
        year = AcademicYear.objects.create(
            school=self.school, name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        Enrollment.objects.create(
            student=self.student, academic_year=year, class_level=level, stream=stream, is_active=True,
        )
        teacher_user = User.objects.create_user("a11_teacher")
        teacher = TeacherProfile.objects.create(user=teacher_user, school=self.school)
        subject = Subject.objects.create(school=self.school, name="Science", code="SCI")
        TeacherAssignment.objects.create(teacher=teacher, school=self.school, subject=subject, stream=stream)
        path = LearningPath.objects.create(scope="school", school=self.school, title="Progress")
        LearningPathParticipation.objects.create(
            profile=self.profile, path=path, path_version=1, last_activity_at=timezone.now(),
        )
        self.client.force_authenticate(teacher_user)
        response = self.client.get(f"{BASE}teachers/learners/{self.student.pk}/summary/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["participation_count"], 1)
        self.assertEqual(response.json()["completed_path_count"], 0)
        self.assertNotIn("events", response.json())
        self.assertNotIn("conversation", response.json())
        other_student = Student.objects.create(
            school=self.school, first_name="Not", last_name="Assigned",
            admission_number="A11-UNASSIGNED", date_of_birth=date(2012, 3, 1),
        )
        self.assertEqual(self.client.get(f"{BASE}teachers/learners/{other_student.pk}/summary/").status_code, 404)
        self.assertTrue(LearningAuditEvent.objects.filter(action="assigned_learner_summary_read").exists())

    def test_unverified_public_minor_guardian_link_cannot_be_used_to_access(self):
        public_user = User.objects.create_user("a11_public_minor")
        public_profile = LearningProfile.objects.create(
            user=public_user, account_kind="public_learner", age_band="10_17",
            consent_state="verified", age_verified_at=timezone.now(),
            age_verification_source="provider", contact_verified_at=timezone.now(),
            contact_verification_channel="sms",
        )
        self.client.force_authenticate(public_user)
        self.assertEqual(self.client.get(f"{BASE}me/").status_code, 403)
        guardian_user = User.objects.create_user("public_guardian")
        self.client.force_authenticate(guardian_user)
        # A pending relationship is not proof of guardian identity or consent.
        LearningGuardianRelationship.objects.create(
            learner=public_profile, guardian=guardian_user, relationship="parent", status="pending",
        )
        self.client.force_authenticate(public_user)
        self.assertEqual(self.client.get(f"{BASE}me/").status_code, 403)
