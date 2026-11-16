"""User-owned learning subscription APIs, isolated from school billing."""

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import (
    LearningAuditEvent,
    LearningProfile,
    LearningSubscription,
    LearningSubscriptionPlan,
)
from .payment_providers import payment_provider_configuration_state
from .permissions import learner_profile_is_eligible
from .subscription_policy import (
    effective_entitlements,
    premium_plan_is_configured,
    public_plan_payload,
    user_is_verified_guardian_for,
)
from .throttles import LearningProfileThrottle


BASE_CAPABILITIES = {
    "individual_billing_separate": True,
    "school_subscription_covers_learning": False,
    "free_tier_available": True,
    "premium_activation_requires_verified_payment": True,
}


def _profile_for_user(request, raw_profile_id=None):
    if raw_profile_id in (None, ""):
        profile = LearningProfile.objects.filter(user=request.user).first()
        return profile, profile is not None
    if isinstance(raw_profile_id, bool):
        return None, False
    try:
        profile_id = int(raw_profile_id)
    except (TypeError, ValueError):
        return None, False
    if profile_id <= 0:
        return None, False
    profile = LearningProfile.objects.select_related("student", "school", "user").filter(pk=profile_id).first()
    if profile is None:
        return None, False
    allowed = profile.user_id == request.user.pk or user_is_verified_guardian_for(profile, request.user)
    return profile, allowed


def _subscription_payload(profile):
    entitlement = effective_entitlements(profile)
    state = payment_provider_configuration_state()
    configured_premium = premium_plan_is_configured()
    checkout_status = (
        state["status"] if not state["provider_ready"]
        else "ready" if configured_premium else "premium_plan_not_configured"
    )
    return {
        **entitlement,
        "checkout_available": bool(state["provider_ready"] and configured_premium),
        "checkout_status": checkout_status,
        **BASE_CAPABILITIES,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([LearningProfileThrottle])
def subscription_plans(request):
    """Return backend-configured individual plans and their access flags."""
    plans = LearningSubscriptionPlan.objects.all().order_by("tier", "code", "pk")
    return Response({"results": [public_plan_payload(plan) for plan in plans]})


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([LearningProfileThrottle])
def subscription_capabilities(request):
    provider = payment_provider_configuration_state()
    configured_premium = premium_plan_is_configured()
    return Response({
        **BASE_CAPABILITIES,
        "provider": provider,
        "premium_plan_configured": configured_premium,
        "checkout_available": bool(provider["provider_ready"] and configured_premium),
        "checkout_status": provider["status"] if not provider["provider_ready"] else "ready" if configured_premium else "premium_plan_not_configured",
        "registration_available": False,
        "registration_status": "account_verification_provider_integration_incomplete",
        "future_school_linking_available": False,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([LearningProfileThrottle])
def my_subscription(request):
    profile = LearningProfile.objects.filter(user=request.user).first()
    if profile is None:
        return Response({"code": "learning_profile_missing", "detail": "No Personalized Learning profile is linked to this Marian account."}, status=404)
    return Response(_subscription_payload(profile))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([LearningProfileThrottle])
def subscription_history(request):
    if set(request.query_params) - {"profile_id"}:
        return Response({"detail": "Unsupported subscription-history filter."}, status=400)
    raw_profile_id = request.query_params.get("profile_id")
    profile, allowed = _profile_for_user(request, raw_profile_id)
    if profile is None or not allowed:
        return Response({"detail": "Not found."}, status=404)
    LearningAuditEvent.objects.create(
        actor=request.user,
        school_id=profile.school_id,
        scope="school" if profile.school_id else "public",
        action="learning_subscription_history_viewed",
        target_type="learning_profile",
        target_id=str(profile.pk),
        safe_details={},
    )
    rows = LearningSubscription.objects.filter(profile=profile).select_related("plan").prefetch_related("transactions").order_by("-created_at", "-pk")[:100]
    results = []
    for subscription in rows:
        results.append({
            "plan_code": subscription.plan.code,
            "plan_name": subscription.plan.name,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "transactions": [
                {
                    "amount": str(event.amount),
                    "currency": event.currency,
                    "status": event.status,
                    "received_at": event.received_at,
                    "provider_verified": event.provider_verified_at is not None,
                }
                for event in subscription.transactions.order_by("-received_at", "-pk")[:50]
            ],
        })
    return Response({"results": results, "truncated": len(results) >= 100})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LearningProfileThrottle])
def request_premium_checkout(request):
    """Fail closed until a real provider, active price, and verification exist."""
    if not isinstance(request.data, dict):
        return Response({"detail": "Send a JSON object."}, status=400)
    unsupported = set(request.data) - {"plan_code", "profile_id"}
    if unsupported:
        return Response({"detail": "Unsupported checkout fields."}, status=400)
    plan_code = request.data.get("plan_code")
    if not isinstance(plan_code, str) or not plan_code.strip() or len(plan_code) > 40:
        return Response({"detail": "Choose a configured premium plan."}, status=400)
    profile, allowed = _profile_for_user(request, request.data.get("profile_id"))
    if profile is None or not allowed:
        return Response({"detail": "Not found."}, status=404)
    if not learner_profile_is_eligible(profile):
        return Response({"code": "learner_not_eligible", "detail": "Age, consent, verification, and account status must be eligible before checkout."}, status=403)
    if not profile.user.is_active:
        return Response({"code": "learner_not_eligible", "detail": "The linked Marian account is not active."}, status=403)

    plan = LearningSubscriptionPlan.objects.filter(code=plan_code, tier="premium").first()
    if plan is None:
        return Response({"detail": "The selected premium plan is unavailable."}, status=404)
    is_owner = profile.user_id == request.user.pk
    is_linked_guardian = user_is_verified_guardian_for(profile, request.user)
    if profile.age_band != "adult" and (is_owner or not is_linked_guardian):
        return Response({"code": "guardian_payer_required", "detail": "A verified linked guardian must manage payment for a minor."}, status=403)
    if not is_owner and not is_linked_guardian:
        return Response({"detail": "Not found."}, status=404)

    provider = payment_provider_configuration_state()
    if not provider["provider_ready"]:
        # Deliberately create no checkout session, payment event, or subscription.
        return Response({
            "code": provider["status"],
            "detail": "Individual checkout is unavailable until a real payment provider and verified webhook flow are integrated.",
            "payment_created": False,
            "premium_activated": False,
        }, status=503)

    if (
        not plan.is_active or plan.amount is None or plan.amount <= 0
        or len(plan.currency) != 3 or not plan.currency.isascii()
        or not plan.currency.isalpha() or not plan.currency.isupper()
        or plan.billing_interval not in {"monthly", "yearly"}
    ):
        return Response({"code": "premium_plan_not_configured", "detail": "Premium pricing is not configured or approved."}, status=503)

    # There is intentionally no adapter invocation in this source copy. A
    # configured module path cannot make checkout operational by itself.
    return Response({
        "code": "payment_adapter_integration_incomplete",
        "detail": "Individual checkout is unavailable until the configured provider is integrated and independently validated.",
        "payment_created": False,
        "premium_activated": False,
    }, status=503)
