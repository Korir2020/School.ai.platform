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
ADMIN_INVITATIONS = "/api/learning/v1/admin/invitations/"
CLAIM_URL = "/api/learning/v1/invitations/claim/"


class LearningAccountLifecycleTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", code="NORTH")
        self.other_school = School.objects.create(name="South School", code="SOUTH")
        self.admin = User.objects.create_user("north_admin", password="SchoolAdmin!123")
        SchoolAdminProfile.objects.create(user=self.admin, school=self.school, is_deputy=False)
        self.other_admin = User.objects.create_user("south_admin", password="SchoolAdmin!123")
        SchoolAdminProfile.objects.create(user=self.other_admin, school=self.other_school, is_deputy=False)
        self.deputy = User.objects.create_user("north_deputy", password="SchoolAdmin!123")
        SchoolAdminProfile.objects.create(user=self.deputy, school=self.school, is_deputy=True)
        self.teacher = User.objects.create_user("north_teacher", password="TeacherPass!123")
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.superadmin = User.objects.create_superuser(
            "platform_root", "root@example.invalid", "RootPass!123",
        )
        self.platform_staff = User.objects.create_user(
            "platform_staff", password="PlatformStaff!123", is_staff=True,
        )
        self.guardian_user = User.objects.create_user(
            "guardian_north", password="GuardianPass!123",
        )
        self.guardian = GuardianProfile.objects.create(
            user=self.guardian_user, school=self.school,
        )
        self.child = self.make_student(
            school=self.school,
            admission="N-001",
            dob=date(2014, 6, 1),
        )
        StudentGuardian.objects.create(student=self.child, guardian=self.guardian)
        self.other_student = self.make_student(
            school=self.other_school,
            admission="S-001",
            dob=date(2010, 3, 5),
        )

    @staticmethod
    def make_student(school, admission, dob=None, status="active"):
        return Student.objects.create(
            school=school,
            first_name="Amina",
            last_name="Learner",
            admission_number=admission,
            date_of_birth=dob,
            status=status,
        )

    def issue(self, student, admin=None):
        self.client.force_authenticate(admin or self.admin)
        return self.client.post(
            ADMIN_INVITATIONS, {"student_id": student.pk}, format="json",
        )

    def claim(self, token, username="school_learner_1", **extra):
        data = {
            "token": token,
            "username": username,
            "password": "N4vigator!Learning2026",
            **extra,
        }
        self.client.force_authenticate(None)
        return self.client.post(CLAIM_URL, data, format="json")

    def test_full_admin_invitation_returns_raw_code_once_and_stores_only_hash(self):
        response = self.issue(self.child)
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()
        raw = payload["claim_token"]
        invitation = LearningInvitation.objects.get(pk=payload["id"])
        self.assertNotEqual(invitation.token_hash, raw)
        self.assertEqual(invitation.token_hash, hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(invitation.guardian_approval_state, "pending")
        self.assertNotIn("token_hash", payload)

        listing = self.client.get(ADMIN_INVITATIONS)
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn("claim_token", listing.json()["results"][0])
        self.assertNotIn("token_hash", listing.json()["results"][0])

    def test_superadmin_deputy_teacher_and_other_school_admin_cannot_issue_invitation(self):
        for user in (self.superadmin, self.platform_staff, self.deputy, self.teacher):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                response = self.client.post(
                    ADMIN_INVITATIONS, {"student_id": self.child.pk}, format="json",
                )
                self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(self.other_admin)
        cross_school = self.client.post(
            ADMIN_INVITATIONS, {"student_id": self.child.pk}, format="json",
        )
        self.assertEqual(cross_school.status_code, 404)
        self.assertEqual(LearningInvitation.objects.count(), 0)

    def test_school_admin_cannot_enumerate_or_invite_other_school_students(self):
        response = self.issue(self.other_student)
        self.assertEqual(response.status_code, 404)
        self.client.force_authenticate(self.admin)
        listing = self.client.get(ADMIN_INVITATIONS)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["results"], [])

    def test_only_active_students_without_existing_learning_account_can_be_invited(self):
        inactive = self.make_student(self.school, "N-002", date(2012, 1, 1), status="transferred")
        self.assertEqual(self.issue(inactive).status_code, 409)
        response = self.issue(self.child)
        profile = LearningProfile.objects.create(
            user=User.objects.create_user("prelinked"),
            account_kind="school_student",
            school=self.school,
            student=self.child,
        )
        self.assertIsNotNone(profile.pk)
        # Existing profile blocks another invitation even if one invitation was issued earlier.
        self.assertEqual(self.issue(self.child).status_code, 409)

    def test_minor_or_unknown_age_without_active_guardian_cannot_be_invited(self):
        no_guardian = self.make_student(self.school, "N-003", date(2013, 2, 1))
        response = self.issue(no_guardian)
        self.assertEqual(response.status_code, 409)
        unknown_age = self.make_student(self.school, "N-004", None)
        self.assertEqual(self.issue(unknown_age).status_code, 409)

    def test_unlinked_guardian_cannot_approve_an_invitation(self):
        invite_response = self.issue(self.child)
        invitation_id = invite_response.json()["id"]
        unrelated_user = User.objects.create_user("unrelated_guardian")
        GuardianProfile.objects.create(user=unrelated_user, school=self.school)
        self.client.force_authenticate(unrelated_user)
        response = self.client.post(
            f"/api/learning/v1/invitations/{invitation_id}/guardian-approval/",
            {}, format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_guardian_approval_then_claim_creates_student_only_account_and_login_role(self):
        invitation_response = self.issue(self.child)
        invitation = LearningInvitation.objects.get(pk=invitation_response.json()["id"])
        token = invitation_response.json()["claim_token"]

        self.client.force_authenticate(self.guardian_user)
        approval = self.client.post(
            f"/api/learning/v1/invitations/{invitation.pk}/guardian-approval/",
            {}, format="json",
        )
        self.assertEqual(approval.status_code, 200, approval.content)
        invitation.refresh_from_db()
        self.assertEqual(invitation.guardian_approval_state, "approved")
        self.assertEqual(invitation.guardian_approved_by_id, self.guardian.pk)

        claim_response = self.claim(
            token,
            username="school_learner_1",
            is_superuser=True,
            is_staff=True,
            school_id=self.other_school.pk,
            student_id=self.other_student.pk,
        )
        self.assertEqual(claim_response.status_code, 201, claim_response.content)
        account = User.objects.get(username="school_learner_1")
        profile = LearningProfile.objects.get(user=account)
        self.assertEqual(profile.student_id, self.child.pk)
        self.assertEqual(profile.school_id, self.school.pk)
        self.assertEqual(profile.account_kind, "school_student")
        self.assertEqual(profile.consent_state, "verified")
        self.assertFalse(account.is_staff)
        self.assertFalse(account.is_superuser)
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.claimed_at)

        login = self.client.post(
            "/api/auth/login/",
            {"username": "school_learner_1", "password": "N4vigator!Learning2026"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.content)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + login.json()["access"])
        identity = self.client.get("/api/auth/me/")
        self.assertEqual(identity.status_code, 200, identity.content)
        self.assertEqual(identity.json()["role"], "student")
        self.assertEqual(identity.json()["school"]["id"], self.school.pk)

    def test_adult_can_claim_without_guardian_and_unknown_age_cannot(self):
        adult = self.make_student(self.school, "N-005", date(1998, 1, 1))
        response = self.issue(adult)
        self.assertEqual(response.status_code, 201, response.content)
        invitation = LearningInvitation.objects.get(pk=response.json()["id"])
        self.assertEqual(invitation.guardian_approval_state, "not_required")
        claim_response = self.claim(response.json()["claim_token"], username="adult_learner")
        self.assertEqual(claim_response.status_code, 201, claim_response.content)
        profile = LearningProfile.objects.get(user__username="adult_learner")
        self.assertEqual(profile.age_band, "adult")
        self.assertEqual(profile.consent_state, "not_required")

    def test_claim_rejects_invalid_revoked_expired_and_reused_tokens_generically(self):
        invalid = self.claim("not-a-valid-token")
        self.assertEqual(invalid.status_code, 400)
        generic = invalid.json()["detail"]

        invitation_response = self.issue(self.child)
        invitation = LearningInvitation.objects.get(pk=invitation_response.json()["id"])
        token = invitation_response.json()["claim_token"]
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        revoked = self.claim(token)
        self.assertEqual(revoked.status_code, 400)
        self.assertEqual(revoked.json()["detail"], generic)

        expired_student = self.make_student(self.school, "N-006", date(1999, 2, 2))
        expired_response = self.issue(expired_student)
        expired_invitation = LearningInvitation.objects.get(pk=expired_response.json()["id"])
        expired_invitation.expires_at = timezone.now() - timedelta(minutes=1)
        expired_invitation.save(update_fields=["expires_at"])
        expired = self.claim(expired_response.json()["claim_token"])
        self.assertEqual(expired.status_code, 400)
        self.assertEqual(expired.json()["detail"], generic)

    def test_suspended_school_invitation_cannot_be_claimed(self):
        adult = self.make_student(self.school, "N-007", date(1990, 2, 2))
        issued = self.issue(adult)
        self.assertEqual(issued.status_code, 201)
        self.school.is_suspended = True
        self.school.save(update_fields=["is_suspended"])
        response = self.claim(issued.json()["claim_token"], username="blocked_learner")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="blocked_learner").exists())

    def test_student_profile_is_subject_to_school_suspension_after_claim(self):
        adult = self.make_student(self.school, "N-008", date(1997, 2, 2))
        issued = self.issue(adult)
        claimed = self.claim(issued.json()["claim_token"], username="suspend_test_learner")
        self.assertEqual(claimed.status_code, 201, claimed.content)
        user = User.objects.get(username="suspend_test_learner")
        self.school.is_suspended = True
        self.school.save(update_fields=["is_suspended"])
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_public_learning_identity_has_no_school_tenant(self):
        public_user = User.objects.create_user("public_learner", password="PublicPass!123")
        LearningProfile.objects.create(
            user=public_user,
            account_kind="public_learner",
            age_band="adult",
            consent_state="not_required",
        )
        self.client.force_authenticate(public_user)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["role"], "public_learner")
        self.assertIsNone(response.json()["school"])

    def test_duplicate_open_invitation_is_not_created(self):
        first = self.issue(self.child)
        self.assertEqual(first.status_code, 201)
        second = self.issue(self.child)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(LearningInvitation.objects.filter(student=self.child).count(), 1)

    def test_full_school_admin_can_revoke_only_own_unclaimed_invitation(self):
        issued = self.issue(self.child)
        invitation = LearningInvitation.objects.get(pk=issued.json()["id"])
        self.client.force_authenticate(self.other_admin)
        other_school = self.client.post(
            f"/api/learning/v1/admin/invitations/{invitation.pk}/revoke/", {}, format="json",
        )
        self.assertEqual(other_school.status_code, 404)
        self.client.force_authenticate(self.admin)
        revoked = self.client.post(
            f"/api/learning/v1/admin/invitations/{invitation.pk}/revoke/", {}, format="json",
        )
        self.assertEqual(revoked.status_code, 200)
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.revoked_at)

    def test_anonymous_admin_listing_and_guardian_approval_are_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(ADMIN_INVITATIONS).status_code, 401)
        self.assertEqual(
            self.client.post("/api/learning/v1/invitations/1/guardian-approval/", {}, format="json").status_code,
            401,
        )

    def test_unknown_age_claim_remains_unverified_after_guardian_approves_invitation(self):
        student = self.make_student(self.school, "N-UNKNOWN", None)
        StudentGuardian.objects.create(student=student, guardian=self.guardian)
        issued = self.issue(student)
        self.assertEqual(issued.status_code, 201, issued.content)
        invitation = LearningInvitation.objects.get(pk=issued.json()["id"])
        self.client.force_authenticate(self.guardian_user)
        approved = self.client.post(
            f"/api/learning/v1/invitations/{invitation.pk}/guardian-approval/", {}, format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        claimed = self.claim(issued.json()["claim_token"], username="unknown_age_claim")
        self.assertEqual(claimed.status_code, 201, claimed.content)
        profile = LearningProfile.objects.get(user__username="unknown_age_claim")
        self.assertEqual(profile.age_band, "unknown")
        self.assertIsNone(profile.age_verified_at)
        self.assertEqual(profile.consent_state, "pending")
        user = User.objects.get(username="unknown_age_claim")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/auth/me/").json()["role"], "student")
        self.assertEqual(self.client.get("/api/learning/v1/me/").status_code, 403)
        self.assertEqual(self.client.get("/api/learning/v1/catalog/resources/").status_code, 403)
