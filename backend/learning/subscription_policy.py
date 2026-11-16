"""Effective subscription and entitlement policy for Personalized Learning."""

from django.db.models import F, Q
from django.utils import timezone

from .models import LearningSubscription, LearningSubscriptionPlan


DEFAULT_FREE_ENTITLEMENTS = {
    "catalog_discovery": True,
    "catalog_search": True,
    "free_resources": True,
    "basic_activities": True,
    "personal_dashboard": True,
    "basic_progress": True,
    "selected_learning_paths": True,
    # No AI tutor endpoint is implemented in this source copy.
    "ai_tutor_requests_per_day": 0,
}


def verified_active_premium_subscription(profile):
    """Fail closed: an active premium plan needs an in-period verified charge."""
    if profile is None or profile.account_status != "active":
        return None
    now = timezone.now()
    if not hasattr(profile, "_effective_premium_subscription"):
        profile._effective_premium_subscription = (
            LearningSubscription.objects.filter(
                profile=profile,
                status="active",
                plan__tier="premium",
                plan__is_active=True,
                current_period_start__lte=now,
                current_period_end__gt=now,
                transactions__status="succeeded",
                transactions__provider_verified_at__isnull=False,
                transactions__provider_transaction_id__gt="",
                transactions__provider__gt="",
                transactions__amount=F("plan__amount"),
                transactions__currency=F("plan__currency"),
            )
            .select_related("plan")
            .order_by("-current_period_end", "-pk")
            .first()
        )
    return profile._effective_premium_subscription


def effective_plan(profile):
    subscription = verified_active_premium_subscription(profile)
    if subscription is not None:
        return subscription.plan, subscription
    free_plan = LearningSubscriptionPlan.objects.filter(
        tier="free", is_active=True,
    ).order_by("code", "pk").first()
    return free_plan, None


def effective_entitlements(profile):
    plan, subscription = effective_plan(profile)
    entitlements = plan.entitlements if plan and isinstance(plan.entitlements, dict) else {}
    if subscription is None:
        if not entitlements:
            entitlements = DEFAULT_FREE_ENTITLEMENTS
        return {
            "tier": "free",
            "plan_code": plan.code if plan else "free",
            "plan_name": plan.name if plan else "Free",
            "subscription_status": "free",
            "entitlements": entitlements,
            "period_end": None,
        }
    return {
        "tier": "premium",
        "plan_code": plan.code,
        "plan_name": plan.name,
        "subscription_status": "active",
        "entitlements": entitlements,
        "period_end": subscription.current_period_end,
    }


def profile_can_access_tier(profile, tier):
    if tier == "free":
        return True
    if tier != "premium":
        return False
    return verified_active_premium_subscription(profile) is not None


def public_plan_payload(plan):
    """Expose only customer-safe plan data; prices are never inferred."""
    amount_configured = plan.tier == "free" or (
        plan.amount is not None and plan.amount > 0
        and len(plan.currency) == 3 and plan.currency.isascii()
        and plan.currency.isalpha() and plan.currency.isupper()
        and plan.billing_interval in {"monthly", "yearly"}
    )
    return {
        "code": plan.code,
        "name": plan.name,
        "tier": plan.tier,
        "description": plan.description,
        "amount": str(plan.amount) if plan.amount is not None else None,
        "currency": plan.currency or None,
        "billing_interval": plan.billing_interval,
        "entitlements": plan.entitlements if isinstance(plan.entitlements, dict) else {},
        "is_active": plan.is_active,
        "price_configured": amount_configured,
    }


def premium_plan_is_configured():
    for plan in LearningSubscriptionPlan.objects.filter(tier="premium", is_active=True):
        if public_plan_payload(plan)["price_configured"]:
            return True
    return False


def user_is_verified_guardian_for(profile, user):
    """Recognize only verified, consented linked guardians; never infer by name."""
    if (
        profile is None or user is None
        or not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
    ):
        return False
    if profile.account_kind == "public_learner":
        from .models import LearningGuardianRelationship

        return LearningGuardianRelationship.objects.filter(
            learner=profile,
            guardian=user,
            status="verified",
            identity_verified_at__isnull=False,
            consent_at__isnull=False,
            consent_withdrawn_at__isnull=True,
        ).exists()
    if profile.account_kind == "school_student" and profile.student_id:
        from schools.models import StudentGuardian

        return StudentGuardian.objects.filter(
            student_id=profile.student_id,
            student__school_id=profile.school_id,
            student__status="active",
            student__school__is_suspended=False,
            guardian__user=user,
        ).exists()
    return False
