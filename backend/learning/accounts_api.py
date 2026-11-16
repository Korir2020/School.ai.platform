"""Activity 11 account operations, privacy-scoped summaries, and disabled flows."""

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.permissions import restrict_for_teacher
from api.suspension import SchoolNotSuspended
from schools.models import (
    GuardianProfile,
    SchoolAdminProfile,
    Student,
    StudentGuardian,
    TeacherAssignment,
    TeacherProfile,
)

from .account_policy import age_on, minimum_independent_age
from .account_providers import provider_configuration_state
from .payment_providers import payment_provider_configuration_state
from .models import (
    LearningAccountLifecycleRequest,
    LearningAuditEvent,
    LearningGuardianRelationship,
    LearningPathParticipation,
    LearningProfile,
    LearningSchoolSettings,
)
from .permissions import FullSchoolLearningAdmin, learner_profile_is_eligible
from .throttles import (
    LearningGuardianThrottle,
    LearningInvitationAdminThrottle,
    LearningLifecycleThrottle,
    LearningProfileThrottle,
)


def _audit(actor, profile, action, details=None):
    LearningAuditEvent.objects.create(
        actor=actor,
        school_id=profile.school_id,
        scope="school" if profile.school_id else "public",
        action=action,
        target_type="learning_profile",
        target_id=str(profile.pk),
        safe_details=details or {},
    )


def _profile_summary(profile):
    participation = LearningPathParticipation.objects.filter(profile=profile).aggregate(
        total=Count("id"), completed=Count("id", filter=Q(state="completed")),
        last_activity=Max("last_activity_at"),
    )
    return {
        "profile_id": profile.pk,
        "age_band": profile.age_band,
        "account_status": profile.account_status,
        "participation_count": participation["total"] or 0,
        "completed_path_count": participation["completed"] or 0,
        "last_activity_at": participation["last_activity"],
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def account_capabilities(request):
    state = provider_configuration_state()
    payment_state = payment_provider_configuration_state()
    return Response({
        "minimum_independent_age": minimum_independent_age(),
        "adult_age": 18,
        "age_policy": {
            "under_minimum": "school_managed_only",
            "minor": "verified_guardian_and_consent_required",
            "adult": "self_registration_allowed_when_verified",
            "unknown": "protected_learning_denied_until_verified",
        },
        "retention_policy_configured": bool(str(getattr(settings, "LEARNING_ACCOUNT_RETENTION_DAYS", "") or "").strip()),
        "deletion_execution_available": False,
        "independent_profile_uses_marian_auth": True,
        "individual_billing_separate_from_school": True,
        "school_subscription_covers_learning": False,
        "premium_payment": payment_state,
        **state,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LearningProfileThrottle])
def independent_registration(request):
    """Do not collect/store registration evidence until a real provider flow is wired."""
    state = provider_configuration_state()
    return Response({
        "code": state["status"],
        "detail": "Independent learning registration is unavailable until real contact, age, and guardian verification providers are integrated.",
        "registration_created": False,
    }, status=503)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LearningLifecycleThrottle])
def account_lifecycle_requests(request):
    """Create/list deletion or suspension requests without destructive deletion."""
    if request.method == "GET":
        rows = LearningAccountLifecycleRequest.objects.filter(requested_by=request.user).order_by("-created_at")[:100]
        return Response({"results": [
            {"id": row.pk, "profile_id": row.profile_id, "request_type": row.request_type,
             "status": row.status, "created_at": row.created_at, "resolved_at": row.resolved_at}
            for row in rows
        ]})

    request_type = request.data.get("request_type")
    if request_type not in {"deletion", "suspension"}:
        return Response({"detail": "request_type must be deletion or suspension."}, status=400)

    profile_id = request.data.get("profile_id")
    if profile_id is None:
        profile = LearningProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response({"detail": "No learning account is assigned."}, status=404)
    else:
        try:
            if isinstance(profile_id, bool):
                raise ValueError
            profile_id = int(profile_id)
        except (TypeError, ValueError):
            return Response({"detail": "profile_id is invalid."}, status=400)
        profile = LearningProfile.objects.filter(pk=profile_id).first()
        if profile is None:
            return Response({"detail": "Not found."}, status=404)
        if profile.user_id != request.user.pk and not _is_verified_guardian(request.user, profile):
            return Response({"detail": "Not found."}, status=404)

    with transaction.atomic():
        profile = LearningProfile.objects.select_for_update().get(pk=profile.pk)
        existing = LearningAccountLifecycleRequest.objects.filter(
            profile=profile, request_type=request_type, status="pending",
        ).first()
        if existing:
            return Response({"id": existing.pk, "status": existing.status, "request_type": existing.request_type})
        if profile.account_status != "active":
            return Response({"detail": "This learning account is not active."}, status=409)
        row, created = LearningAccountLifecycleRequest.objects.get_or_create(
            profile=profile,
            request_type=request_type,
            status="pending",
            defaults={
                "requested_by": request.user,
                "reason_code": "guardian_request" if profile.user_id != request.user.pk else "self_requested",
                "previous_account_status": profile.account_status,
            },
        )
        if not created:
            return Response({"id": row.pk, "status": row.status, "request_type": row.request_type})
        profile.account_status = "pending_deletion" if request_type == "deletion" else "suspended"
        profile.save(update_fields=["account_status", "updated_at"])
        _audit(request.user, profile, "account_deletion_requested" if request_type == "deletion" else "account_suspension_requested", {"request_id": row.pk})
    return Response({"id": row.pk, "status": row.status, "request_type": row.request_type,
                     "detail": "Request recorded. No data has been permanently deleted."}, status=201)


def _is_verified_guardian(user, profile):
    if profile.account_kind == "school_student" and profile.student_id:
        return StudentGuardian.objects.filter(
            student_id=profile.student_id,
            student__school_id=profile.school_id,
            guardian__school_id=profile.school_id,
            guardian__user=user,
            guardian__user__is_active=True,
        ).exists()
    return LearningGuardianRelationship.objects.filter(
        learner=profile, guardian=user, status="verified",
        identity_verified_at__isnull=False, consent_at__isnull=False,
        consent_withdrawn_at__isnull=True,
    ).exists()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LearningLifecycleThrottle])
def cancel_account_lifecycle_request(request, request_id):
    with transaction.atomic():
        row = LearningAccountLifecycleRequest.objects.select_for_update().filter(
            pk=request_id, requested_by=request.user, status="pending",
        ).select_related("profile").first()
        if row is None:
            return Response({"detail": "Not found."}, status=404)
        profile = LearningProfile.objects.select_for_update().get(pk=row.profile_id)
        row.status = "cancelled"
        row.resolved_at = timezone.now()
        row.save(update_fields=["status", "resolved_at"])
        if profile.account_status in {"pending_deletion", "suspended"}:
            profile.account_status = row.previous_account_status
            profile.save(update_fields=["account_status", "updated_at"])
        _audit(request.user, profile, "account_lifecycle_request_cancelled", {"request_id": row.pk})
    return Response({"id": row.pk, "status": row.status})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([LearningGuardianThrottle])
def guardian_learners(request):
    """Return minimal summaries only for learners verifiably linked to this guardian."""
    results = []
    school_guardians = GuardianProfile.objects.filter(
        user=request.user, user__is_active=True,
    ).values_list("pk", "school_id")
    for guardian_id, school_id in school_guardians:
        links = StudentGuardian.objects.filter(
            guardian_id=guardian_id, student__school_id=school_id,
            student__school__is_suspended=False,
            student__status="active",
            student__learning_profile__isnull=False,
        ).select_related("student__learning_profile")
        for link in links:
            profile = link.student.learning_profile
            _audit(request.user, profile, "guardian_learning_summary_read")
            summary = _profile_summary(profile) if learner_profile_is_eligible(profile) else {
                "profile_id": profile.pk,
                "age_band": profile.age_band,
                "account_status": profile.account_status,
                "participation_count": 0,
                "completed_path_count": 0,
                "last_activity_at": None,
            }
            summary["learner_name"] = f"{link.student.first_name} {link.student.last_name}".strip()
            summary["consent_state"] = profile.consent_state
            results.append(summary)

    public_links = LearningGuardianRelationship.objects.filter(
        guardian=request.user, status="verified", identity_verified_at__isnull=False,
        consent_at__isnull=False, consent_withdrawn_at__isnull=True,
        learner__account_kind="public_learner", learner__account_status="active",
    ).select_related("learner")
    for link in public_links:
        profile = link.learner
        _audit(request.user, profile, "guardian_learning_summary_read")
        summary = _profile_summary(profile) if learner_profile_is_eligible(profile) else {
            "profile_id": profile.pk,
            "age_band": profile.age_band,
            "account_status": profile.account_status,
            "participation_count": 0,
            "completed_path_count": 0,
            "last_activity_at": None,
        }
        summary["consent_state"] = profile.consent_state
        results.append(summary)
    return Response({"results": results})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LearningGuardianThrottle])
def withdraw_guardian_consent(request, profile_id):
    profile = LearningProfile.objects.filter(pk=profile_id).first()
    if profile is None or not _is_verified_guardian(request.user, profile):
        return Response({"detail": "Not found."}, status=404)
    with transaction.atomic():
        profile = LearningProfile.objects.select_for_update().get(pk=profile.pk)
        now = timezone.now()
        if profile.account_kind == "public_learner":
            LearningGuardianRelationship.objects.filter(
                learner=profile, guardian=request.user, status="verified",
                consent_withdrawn_at__isnull=True,
            ).update(status="withdrawn", consent_withdrawn_at=now)
        if profile.consent_state == "withdrawn":
            return Response({"detail": "Guardian consent is already withdrawn."})
        profile.consent_state = "withdrawn"
        profile.save(update_fields=["consent_state", "updated_at"])
        _audit(request.user, profile, "guardian_consent_withdrawn")
    return Response({"detail": "Consent withdrawn. Protected learning access is now blocked."})


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended])
@throttle_classes([LearningProfileThrottle])
def assigned_learner_summary(request, student_id):
    teacher = TeacherProfile.objects.filter(user=request.user, user__is_active=True).first()
    if teacher is None or SchoolAdminProfile.objects.filter(user=request.user).exists() or request.user.is_staff or request.user.is_superuser:
        return Response({"detail": "Not found."}, status=404)
    assigned_streams = TeacherAssignment.objects.filter(
        teacher=teacher, school_id=teacher.school_id,
    ).values_list("stream_id", flat=True)
    student_qs = restrict_for_teacher(request.user, Student.objects.filter(
        pk=student_id,
        school_id=teacher.school_id,
        status="active",
        enrollment__is_active=True,
        enrollment__academic_year__is_active=True,
        enrollment__stream_id__in=assigned_streams,
    ))
    student = student_qs.select_related("learning_profile").first()
    if student is None or not hasattr(student, "learning_profile"):
        return Response({"detail": "Not found."}, status=404)
    profile = student.learning_profile
    if not learner_profile_is_eligible(profile):
        return Response({"detail": "Not found."}, status=404)
    school_settings = LearningSchoolSettings.objects.filter(school_id=profile.school_id).first()
    if school_settings and not school_settings.teacher_studio_enabled:
        return Response({"detail": "Not found."}, status=404)
    age = age_on(student.date_of_birth)
    if school_settings and (
        not school_settings.learning_access_enabled
        or age is None
        or age < school_settings.minimum_learner_age
        or age > school_settings.maximum_learner_age
    ):
        return Response({"detail": "Not found."}, status=404)
    _audit(request.user, profile, "assigned_learner_summary_read")
    result = _profile_summary(profile)
    result["student_id"] = student.pk
    result["learner_name"] = f"{student.first_name} {student.last_name}".strip()
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningAdmin])
@throttle_classes([LearningProfileThrottle])
def school_learning_summary(request):
    school_id = request.learning_school_admin.school_id
    profiles = LearningProfile.objects.filter(school_id=school_id, account_kind="school_student")
    aggregate = LearningPathParticipation.objects.filter(profile__in=profiles).aggregate(
        total=Count("id"), completed=Count("id", filter=Q(state="completed")),
        last_activity=Max("last_activity_at"),
    )
    LearningAuditEvent.objects.create(
        actor=request.user, school_id=school_id, scope="school",
        action="school_learning_aggregate_read", target_type="school", target_id=str(school_id),
    )
    return Response({
        "learner_count": profiles.count(),
        "active_account_count": profiles.filter(account_status="active").count(),
        "suspended_account_count": profiles.filter(account_status="suspended").count(),
        "participation_count": aggregate["total"] or 0,
        "completed_path_count": aggregate["completed"] or 0,
        "last_activity_at": aggregate["last_activity"],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningAdmin])
@throttle_classes([LearningProfileThrottle])
def school_learning_accounts(request):
    school_id = request.learning_school_admin.school_id
    profiles = list(
        LearningProfile.objects.filter(
            school_id=school_id, account_kind="school_student",
        ).select_related("student").order_by("student__last_name", "student__first_name", "pk")[:200]
    )
    LearningAuditEvent.objects.create(
        actor=request.user, school_id=school_id, scope="school",
        action="school_learning_accounts_list_read", target_type="school", target_id=str(school_id),
        safe_details={"count": len(profiles)},
    )
    return Response({
        "results": [
            {
                "profile_id": profile.pk,
                "student_name": f"{profile.student.first_name} {profile.student.last_name}".strip(),
                "age_band": profile.age_band,
                "consent_state": profile.consent_state,
                "account_status": profile.account_status,
            }
            for profile in profiles
        ],
        "truncated": len(profiles) == 200,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningAdmin])
@throttle_classes([LearningInvitationAdminThrottle])
def set_school_learner_account_state(request, profile_id):
    state = request.data.get("account_status")
    if state not in {"active", "suspended"}:
        return Response({"detail": "account_status must be active or suspended."}, status=400)
    profile = LearningProfile.objects.filter(
        pk=profile_id, school_id=request.learning_school_admin.school_id,
        account_kind="school_student",
    ).first()
    if profile is None:
        return Response({"detail": "Not found."}, status=404)
    with transaction.atomic():
        profile = LearningProfile.objects.select_for_update().get(pk=profile.pk)
        if profile.account_status in {"pending_deletion", "closed"}:
            return Response({"detail": "This account is under a separate lifecycle state."}, status=409)
        previous = profile.account_status
        profile.account_status = state
        profile.save(update_fields=["account_status", "updated_at"])
        if previous != state:
            _audit(request.user, profile, "school_learner_account_state_changed", {"from": previous, "to": state})
    return Response({"profile_id": profile.pk, "account_status": profile.account_status})


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningAdmin])
@throttle_classes([LearningInvitationAdminThrottle])
def resend_learning_invitation(request, invitation_id):
    from .models import LearningInvitation

    invitation = LearningInvitation.objects.filter(
        pk=invitation_id, school_id=request.learning_school_admin.school_id,
    ).first()
    if invitation is None:
        return Response({"detail": "Not found."}, status=404)
    if invitation.claimed_at or invitation.revoked_at or invitation.expires_at <= timezone.now():
        return Response({"detail": "Invitation is no longer available."}, status=409)
    state = provider_configuration_state()
    LearningAuditEvent.objects.create(
        actor=request.user,
        school_id=invitation.school_id,
        scope="school",
        action="invitation_delivery_unavailable",
        target_type="student",
        target_id=str(invitation.student_id),
        safe_details={"invitation_id": invitation.pk, "provider_state": state["status"]},
    )
    return Response({
        "code": state["status"],
        "delivery_status": invitation.delivery_status,
        "detail": "Invitation delivery is unavailable; no email or SMS was sent and no token was changed.",
    }, status=503)
