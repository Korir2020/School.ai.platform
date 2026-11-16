"""School-managed learner identity and invitation endpoints.

Independent registration remains unavailable until real verification providers
and lifecycle orchestration are integrated.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.suspension import SchoolNotSuspended
from schools.models import Student, StudentGuardian

from .models import LearningAuditEvent, LearningInvitation, LearningProfile
from .account_policy import age_band_for
from .permissions import FullSchoolLearningAdmin, LinkedLearningGuardian
from .throttles import (
    LearningClaimThrottle,
    LearningGuardianThrottle,
    LearningInvitationAdminThrottle,
)

User = get_user_model()
CLAIM_FAILURE = "Unable to claim this learning invitation."


def _age_band(date_of_birth, today=None):
    """Return the shared, privacy-minimized age band and internal exact age."""
    return age_band_for(date_of_birth, today=today)


def _invitation_row(invitation):
    """Safe administrator response; never expose token hashes or raw claim codes."""
    student = invitation.student
    return {
        "id": invitation.id,
        "student_id": student.id,
        "student_name": f"{student.first_name} {student.last_name}".strip(),
        "guardian_approval_state": invitation.guardian_approval_state,
        "delivery_status": invitation.delivery_status,
        "delivery_updated_at": invitation.delivery_updated_at,
        "expires_at": invitation.expires_at,
        "claimed_at": invitation.claimed_at,
        "revoked_at": invitation.revoked_at,
        "created_at": invitation.created_at,
    }


def _student_has_active_guardian(student):
    return StudentGuardian.objects.filter(
        student_id=student.pk,
        student__school_id=student.school_id,
        guardian__school_id=student.school_id,
        guardian__user__is_active=True,
    ).exists()


def _valid_approved_guardian(invitation):
    if (
        invitation.guardian_approval_state != "approved"
        or not invitation.guardian_approved_by_id
        or not invitation.guardian_approved_at
    ):
        return False
    return StudentGuardian.objects.filter(
        student_id=invitation.student_id,
        student__school_id=invitation.school_id,
        guardian_id=invitation.guardian_approved_by_id,
        guardian__school_id=invitation.school_id,
        guardian__user__is_active=True,
    ).exists()


def _issue_school_invitation(request, school_admin, raw_student_id):
    """Validate and issue one school invitation (shared by single and bulk)."""
    try:
        student_id = int(raw_student_id)
        if isinstance(raw_student_id, bool) or student_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return Response({"detail": "student_id must identify an active student in your school."}, status=400)

    student = Student.objects.select_related("school").filter(
        pk=student_id, school_id=school_admin.school_id,
    ).first()
    if student is None:
        return Response({"detail": "Student not found."}, status=404)
    if student.status != "active":
        return Response({"detail": "Only active students may be invited."}, status=409)
    if LearningProfile.objects.filter(student_id=student.pk).exists():
        return Response({"detail": "This student already has a learning account."}, status=409)

    age_band, age = _age_band(student.date_of_birth)
    guardian_required = age_band != "adult"
    if guardian_required and not _student_has_active_guardian(student):
        return Response({
            "detail": "A student with a minor or unknown age needs an active linked guardian before an invitation can be issued."
        }, status=409)

    raw_token = secrets.token_urlsafe(32)
    invitation_ttl = timedelta(
        hours=max(1, min(720, int(getattr(settings, "LEARNING_INVITATION_TTL_HOURS", 168))))
    )
    guardian_state = "pending" if guardian_required else "not_required"
    try:
        with transaction.atomic():
            now = timezone.now()
            existing = LearningInvitation.objects.select_for_update().filter(
                student=student, claimed_at__isnull=True, revoked_at__isnull=True,
            ).order_by("-created_at", "-pk").first()
            if existing and existing.expires_at > now:
                return Response({"detail": "An open invitation already exists for this student."}, status=409)
            if existing:
                existing.revoked_at = now
                existing.save(update_fields=["revoked_at"])
                LearningAuditEvent.objects.create(
                    actor=request.user,
                    school_id=school_admin.school_id,
                    scope="school",
                    action="expired_invitation_retired_for_reissue",
                    target_type="student",
                    target_id=str(student.pk),
                    safe_details={"invitation_id": existing.pk},
                )
            invitation = LearningInvitation.objects.create(
                student=student,
                school_id=school_admin.school_id,
                created_by=request.user,
                token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
                expires_at=now + invitation_ttl,
                guardian_approval_state=guardian_state,
                delivery_status="manual_handoff_required",
            )
            LearningAuditEvent.objects.create(
                actor=request.user,
                school_id=school_admin.school_id,
                scope="school",
                action="invitation_created",
                target_type="student",
                target_id=str(student.pk),
                safe_details={"invitation_id": invitation.pk, "guardian_required": guardian_required},
            )
    except IntegrityError:
        return Response({"detail": "An open invitation already exists for this student."}, status=409)

    # This raw code is returned once to the full school administrator for
    # manual secure handoff; no delivery provider is configured or simulated.
    return Response({
        **_invitation_row(invitation),
        "claim_token": raw_token,
        "claim_token_delivery": "Give this one-time code to the learner's linked guardian; it will not be shown again.",
    }, status=201)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningAdmin])
@throttle_classes([LearningInvitationAdminThrottle])
def admin_invitations(request):
    """List or issue an invitation for an active student in the caller's school."""
    school_admin = request.learning_school_admin
    if request.method == "GET":
        rows = list(
            LearningInvitation.objects.filter(school_id=school_admin.school_id)
            .select_related("student")
            .order_by("-created_at", "-pk")[:200]
        )
        LearningAuditEvent.objects.create(
            actor=request.user,
            school_id=school_admin.school_id,
            scope="school",
            action="school_invitation_list_read",
            target_type="school",
            target_id=str(school_admin.school_id),
            safe_details={"count": len(rows), "truncated": len(rows) == 200},
        )
        return Response({
            "results": [_invitation_row(row) for row in rows],
            "truncated": len(rows) == 200,
        })

    return _issue_school_invitation(
        request, school_admin, request.data.get("student_id"))


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningAdmin])
@throttle_classes([LearningInvitationAdminThrottle])
def admin_invitation_candidates(request):
    """Return a bounded, minimal own-school roster for invitation creation."""
    school_id = request.learning_school_admin.school_id
    now = timezone.now()
    profiles = LearningProfile.objects.filter(student_id=OuterRef("pk"))
    open_invitations = LearningInvitation.objects.filter(
        student_id=OuterRef("pk"), claimed_at__isnull=True, revoked_at__isnull=True,
        expires_at__gt=now,
    )
    active_guardians = StudentGuardian.objects.filter(
        student_id=OuterRef("pk"),
        student__school_id=school_id,
        guardian__school_id=school_id,
        guardian__user__is_active=True,
    )
    students = list(
        Student.objects.filter(school_id=school_id, status="active")
        .annotate(
            has_learning_account=Exists(profiles),
            has_open_invitation=Exists(open_invitations),
            has_active_guardian=Exists(active_guardians),
        )
        .filter(has_learning_account=False, has_open_invitation=False)
        .order_by("last_name", "first_name", "pk")[:201]
    )
    truncated = len(students) > 200
    students = students[:200]
    LearningAuditEvent.objects.create(
        actor=request.user,
        school_id=school_id,
        scope="school",
        action="school_invitation_candidates_read",
        target_type="school",
        target_id=str(school_id),
        safe_details={"count": len(students), "truncated": truncated},
    )
    return Response({
        "results": [
            {
                "student_id": student.pk,
                "student_name": f"{student.first_name} {student.last_name}".strip(),
                "age_band": _age_band(student.date_of_birth)[0],
                "guardian_required": _age_band(student.date_of_birth)[0] != "adult",
                "guardian_available": student.has_active_guardian,
            }
            for student in students
        ],
        "truncated": truncated,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningAdmin])
@throttle_classes([LearningInvitationAdminThrottle])
def revoke_invitation(request, invitation_id):
    school_admin = request.learning_school_admin
    with transaction.atomic():
        invitation = LearningInvitation.objects.select_for_update().filter(
            pk=invitation_id, school_id=school_admin.school_id,
        ).first()
        if invitation is None:
            return Response({"detail": "Not found."}, status=404)
        if invitation.claimed_at:
            return Response({"detail": "A claimed invitation cannot be revoked."}, status=409)
        if invitation.revoked_at:
            return Response({"detail": "Invitation is already revoked."}, status=409)
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        LearningAuditEvent.objects.create(
            actor=request.user,
            school_id=school_admin.school_id,
            scope="school",
            action="invitation_revoked",
            target_type="student",
            target_id=str(invitation.student_id),
            safe_details={"invitation_id": invitation.pk},
        )
    return Response({"detail": "Invitation revoked."})


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, LinkedLearningGuardian])
@throttle_classes([LearningGuardianThrottle])
def guardian_approve_invitation(request, invitation_id):
    """Approve only an invitation for a student linked to the authenticated guardian."""
    guardian = request.learning_guardian
    with transaction.atomic():
        invitation = (
            LearningInvitation.objects.select_for_update()
            .select_related("student", "school")
            .filter(
                pk=invitation_id,
                school_id=guardian.school_id,
                student__guardians__guardian_id=guardian.pk,
                student__school_id=guardian.school_id,
            )
            .distinct()
            .first()
        )
        if invitation is None:
            return Response({"detail": "Not found."}, status=404)
        now = timezone.now()
        if invitation.claimed_at or invitation.revoked_at or invitation.expires_at <= now:
            return Response({"detail": "Invitation is no longer available."}, status=409)
        if invitation.guardian_approval_state == "approved":
            return Response({"detail": "Guardian approval is already recorded."})
        if invitation.guardian_approval_state != "pending":
            return Response({"detail": "Guardian approval is not required for this invitation."}, status=409)

        invitation.guardian_approval_state = "approved"
        invitation.guardian_approved_by = guardian
        invitation.guardian_approved_at = now
        invitation.save(update_fields=[
            "guardian_approval_state", "guardian_approved_by", "guardian_approved_at",
        ])
        LearningAuditEvent.objects.create(
            actor=request.user,
            school_id=guardian.school_id,
            scope="school",
            action="guardian_approved_invitation",
            target_type="student",
            target_id=str(invitation.student_id),
            safe_details={"invitation_id": invitation.pk},
        )
    return Response({"detail": "Guardian approval recorded."})


@api_view(["GET"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, LinkedLearningGuardian])
@throttle_classes([LearningGuardianThrottle])
def guardian_pending_invitations(request):
    """List only unexpired pending invitations for the authenticated guardian's linked students."""
    guardian = request.learning_guardian
    rows = list(
        LearningInvitation.objects.filter(
            school_id=guardian.school_id,
            student__school_id=guardian.school_id,
            student__guardians__guardian_id=guardian.pk,
            student__status="active",
            guardian_approval_state="pending",
            claimed_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("student")
        .distinct()
        .order_by("expires_at", "pk")[:101]
    )
    truncated = len(rows) > 100
    rows = rows[:100]
    LearningAuditEvent.objects.create(
        actor=request.user,
        school_id=guardian.school_id,
        scope="school",
        action="guardian_pending_invitation_list_read",
        target_type="guardian",
        target_id=str(guardian.pk),
        safe_details={"count": len(rows), "truncated": truncated},
    )
    return Response({
        "results": [
            {
                "id": invitation.pk,
                "student_name": f"{invitation.student.first_name} {invitation.student.last_name}".strip(),
                "expires_at": invitation.expires_at,
                "created_at": invitation.created_at,
            }
            for invitation in rows
        ],
        "truncated": truncated,
    })


def _claim_error():
    # Same generic response for invalid, expired, revoked, claimed, unapproved,
    # suspended-school, and otherwise unusable claim codes.
    return Response({"detail": CLAIM_FAILURE}, status=400)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([LearningClaimThrottle])
def claim_student_account(request):
    """Create a basic Marian user and link it to exactly the invited student."""
    token = str(request.data.get("token") or "").strip()
    username = str(request.data.get("username") or "").strip()
    password = request.data.get("password")
    if not token or len(token) > 256 or not username or not isinstance(password, str):
        return _claim_error()

    username_field_name = User.USERNAME_FIELD
    username_field = User._meta.get_field(username_field_name)
    if len(username) > username_field.max_length:
        return _claim_error()
    try:
        username_field.run_validators(username)
    except DjangoValidationError:
        return _claim_error()
    username_lookup = {f"{username_field_name}__iexact": username}
    if User.objects.filter(**username_lookup).exists():
        return Response({"detail": "Choose a different username."}, status=400)

    candidate = User(**{username_field_name: username})
    try:
        validate_password(password, user=candidate)
    except DjangoValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    try:
        with transaction.atomic():
            invitation = (
                LearningInvitation.objects.select_for_update()
                .select_related("student__school", "school", "guardian_approved_by")
                .filter(token_hash=token_hash)
                .first()
            )
            now = timezone.now()
            if (
                invitation is None
                or invitation.claimed_at is not None
                or invitation.revoked_at is not None
                or invitation.expires_at <= now
                or invitation.school.is_suspended
                or invitation.student.school_id != invitation.school_id
                or invitation.student.status != "active"
                or LearningProfile.objects.filter(student_id=invitation.student_id).exists()
            ):
                return _claim_error()

            age_band, _age = _age_band(invitation.student.date_of_birth)
            requires_guardian = (
                age_band != "adult"
                or invitation.guardian_approval_state != "not_required"
            )
            if requires_guardian and not _valid_approved_guardian(invitation):
                return _claim_error()

            # Keep tenant-account and platform privilege flags explicitly false.
            user_kwargs = {username_field_name: username}
            with transaction.atomic():
                user = User.objects.create_user(**user_kwargs, password=password)
                update_fields = []
                if hasattr(user, "is_active"):
                    user.is_active = True
                    update_fields.append("is_active")
                if hasattr(user, "is_staff"):
                    user.is_staff = False
                    update_fields.append("is_staff")
                if hasattr(user, "is_superuser"):
                    user.is_superuser = False
                    update_fields.append("is_superuser")
                if update_fields:
                    user.save(update_fields=update_fields)

            profile = LearningProfile(
                user=user,
                account_kind="school_student",
                school_id=invitation.school_id,
                student_id=invitation.student_id,
                age_band=age_band,
                # Guardian approval of a school invitation is not age
                # verification. An unknown-age account remains protected.
                age_verified_at=now if age_band != "unknown" else None,
                age_verification_source="school_roster" if age_band != "unknown" else "",
                consent_state=(
                    "pending" if age_band == "unknown" and requires_guardian
                    else "verified" if requires_guardian else "not_required"
                ),
                locale="en",
            )
            profile.full_clean()
            profile.save()
            invitation.claimed_at = now
            invitation.save(update_fields=["claimed_at"])
            LearningAuditEvent.objects.create(
                actor=user,
                school_id=invitation.school_id,
                scope="school",
                action="student_account_claimed",
                target_type="student",
                target_id=str(invitation.student_id),
                safe_details={"invitation_id": invitation.pk},
            )
    except IntegrityError:
        # Includes concurrent token redemption and a username race. The whole
        # transaction rolls back, so no orphan User or partially linked profile remains.
        return Response({"detail": "The invitation could not be claimed. Check the username and try again."}, status=409)

    return Response({
        "detail": "Learning account created. Sign in using the new username and password.",
        "username": username,
        "role": "student",
    }, status=201)


BULK_INVITATION_MAX = 50


@api_view(["POST"])
@permission_classes([IsAuthenticated, SchoolNotSuspended, FullSchoolLearningAdmin])
@throttle_classes([LearningInvitationAdminThrottle])
def admin_invitations_bulk(request):
    """Issue invitations for several students using the single-invite rules."""
    school_admin = request.learning_school_admin
    ids = request.data.get("student_ids")
    if not isinstance(ids, list) or not ids or len(ids) > BULK_INVITATION_MAX:
        return Response({
            "detail": f"student_ids must be a list of 1 to {BULK_INVITATION_MAX} students."
        }, status=400)
    seen, results = set(), []
    for raw in ids:
        key = raw if isinstance(raw, (int, str)) else repr(raw)
        if key in seen:
            continue
        seen.add(key)
        response = _issue_school_invitation(request, school_admin, raw)
        results.append({
            "student_id": raw if isinstance(raw, (int, str)) else None,
            "status": response.status_code,
            "result": response.data,
        })
    created = sum(1 for r in results if r["status"] == 201)
    LearningAuditEvent.objects.create(
        actor=request.user,
        school_id=school_admin.school_id,
        scope="school",
        action="school_invitations_bulk_issued",
        target_type="school",
        target_id=str(school_admin.school_id),
        safe_details={"requested": len(results), "created": created},
    )
    return Response({"results": results, "created": created}, status=200)
