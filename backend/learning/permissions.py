from rest_framework.permissions import BasePermission

from schools.models import GuardianProfile, SchoolAdminProfile, TeacherProfile
from .account_policy import age_on
from .models import LearningSchoolSettings


class FullSchoolLearningAdmin(BasePermission):
    """Allow only an active, full school administrator for learning invitations.

    Superusers and Django staff are deliberately not treated as school admins;
    platform privileges do not implicitly grant tenant-level account actions.
    Deputies are excluded until a product policy grants them this permission.
    """

    message = "Only a full school administrator can manage learning invitations."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or user.is_superuser or user.is_staff:
            return False
        profile = (
            SchoolAdminProfile.objects.select_related("school")
            .filter(user=user, user__is_active=True, is_deputy=False)
            .first()
        )
        if profile is None:
            return False
        request.learning_school_admin = profile
        return True


class LinkedLearningGuardian(BasePermission):
    """Require an authenticated Marian guardian profile; student linkage is checked per invite."""

    message = "Guardian access is not assigned."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or user.is_superuser or user.is_staff:
            return False
        guardian = (
            GuardianProfile.objects.select_related("school")
            .filter(user=user, user__is_active=True)
            .first()
        )
        if guardian is None:
            return False
        request.learning_guardian = guardian
        return True


class ActiveLearnerSelfService(BasePermission):
    """Attach only the caller's own active learner profile to the request."""

    message = "An active learning account is not assigned."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        from .models import LearningProfile

        profile = LearningProfile.objects.select_related(
            "school", "student",
        ).filter(user=user).first()
        if profile is None or not learner_profile_is_eligible(profile):
            return False

        if profile.account_kind == "school_student":
            school_settings = LearningSchoolSettings.objects.filter(school_id=profile.school_id).first()
            if school_settings:
                age = age_on(profile.student.date_of_birth)
                if (
                    not school_settings.learning_access_enabled
                    or age is None
                    or age < school_settings.minimum_learner_age
                    or age > school_settings.maximum_learner_age
                ):
                    return False

        request.learning_profile = profile
        return True


def learner_profile_is_eligible(profile):
    """Apply the same fail-closed age, consent, verification and lifecycle gate."""
    if profile is None or profile.account_status != "active":
        return False

    if profile.account_kind == "school_student":
        if (
            profile.school_id is None
            or profile.student_id is None
            or profile.student.school_id != profile.school_id
            or profile.student.status != "active"
        ):
            return False
        from .account_policy import age_band_for

        official_band, exact_age = age_band_for(profile.student.date_of_birth)
        # The linked Marian school roster is the trusted age source for
        # school-managed learners. Unknown or mismatched age always fails.
        if exact_age is None or profile.age_band != official_band:
            return False
        school_settings = LearningSchoolSettings.objects.filter(school_id=profile.school_id).first()
        if school_settings and (
            not school_settings.learning_access_enabled
            or exact_age < school_settings.minimum_learner_age
            or exact_age > school_settings.maximum_learner_age
        ):
            return False
        if official_band != "adult":
            if profile.consent_state != "verified":
                return False
        elif profile.consent_state not in {"verified", "not_required"}:
            return False
    elif profile.account_kind == "public_learner":
        if (
            profile.school_id is not None
            or profile.student_id is not None
            or profile.age_band not in {"10_17", "adult"}
            or profile.age_verified_at is None
            or profile.age_verification_source != "provider"
            or profile.contact_verified_at is None
            or profile.contact_verification_channel not in {"email", "sms"}
        ):
            return False
        if profile.age_band == "adult":
            if profile.consent_state not in {"verified", "not_required"}:
                return False
        else:
            from .models import LearningGuardianRelationship

            if profile.consent_state != "verified" or not LearningGuardianRelationship.objects.filter(
                learner=profile, status="verified", identity_verified_at__isnull=False,
                consent_at__isnull=False, consent_withdrawn_at__isnull=True,
            ).exists():
                return False
    else:
        # Staff profiles and their permissions belong to a later activity.
        return False
    return True


class SchoolContentAuthor(BasePermission):
    """Attach the caller's real Marian teacher or full-admin role and school."""

    message = "Learning-content authoring is not assigned to this account."

    def has_permission(self, request, view):
        user = request.user
        if (
            not user or not user.is_authenticated or not user.is_active
            or user.is_superuser or user.is_staff
        ):
            return False

        teacher = TeacherProfile.objects.select_related("school").filter(
            user=user, user__is_active=True,
        ).first()
        admin = SchoolAdminProfile.objects.select_related("school").filter(
            user=user, user__is_active=True, is_deputy=False,
        ).first()
        # Conflicting role records fail closed rather than combining powers.
        if (teacher is None) == (admin is None):
            return False
        if teacher is not None:
            school_settings = LearningSchoolSettings.objects.filter(school_id=teacher.school_id).first()
            if school_settings and not school_settings.teacher_studio_enabled:
                return False
        request.learning_content_actor = admin or teacher
        request.learning_content_role = "school_admin" if admin else "teacher"
        return True


class TeacherLearningStudio(BasePermission):
    """Allow only a real, active teacher role; platform and admin roles never inherit it."""

    message = "Teacher Learning Studio access is not assigned to this account."

    def has_permission(self, request, view):
        user = request.user
        if (
            not user or not user.is_authenticated or not user.is_active
            or user.is_superuser or user.is_staff
            or SchoolAdminProfile.objects.filter(user=user).exists()
        ):
            return False
        teacher = TeacherProfile.objects.select_related("school").filter(
            user=user, user__is_active=True,
        ).first()
        if teacher is None:
            return False
        school_settings = LearningSchoolSettings.objects.filter(school_id=teacher.school_id).first()
        if school_settings and not school_settings.teacher_studio_enabled:
            return False
        request.learning_school_teacher = teacher
        return True


class FullSchoolContentReviewer(BasePermission):
    """Review only as an active, non-deputy school admin, never as platform staff."""

    message = "Only a full school administrator can review learning content."

    def has_permission(self, request, view):
        user = request.user
        if (
            not user or not user.is_authenticated or not user.is_active
            or user.is_superuser or user.is_staff
        ):
            return False
        admin = SchoolAdminProfile.objects.select_related("school").filter(
            user=user, user__is_active=True, is_deputy=False,
        ).first()
        teacher = TeacherProfile.objects.filter(user=user, user__is_active=True).exists()
        if admin is None or teacher:
            return False
        request.learning_content_actor = admin
        request.learning_content_role = "school_admin"
        return True
