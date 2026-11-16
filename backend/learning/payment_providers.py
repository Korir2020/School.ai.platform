"""Provider-neutral payment boundary for individual learning subscriptions.

This project copy intentionally has no payment adapter. A configured import path
is descriptive only; checkout, webhook processing, and premium activation remain
unavailable until a real adapter is reviewed and integrated.
"""

from typing import Protocol

from django.conf import settings


class LearningPaymentProvider(Protocol):
    """Contract for a future server-side provider implementation."""

    def is_ready(self) -> bool: ...

    def create_checkout(self, *, plan_code: str, payer_reference: str, learner_reference: str) -> object: ...

    def verify_event(self, *, headers: dict, body: bytes) -> object | None: ...

    def cancel_subscription(self, *, provider_subscription_id: str) -> object: ...


def payment_provider_configuration_state():
    """Return truthful capability state without importing unreviewed adapters."""
    configured = bool(str(getattr(settings, "LEARNING_PAYMENT_PROVIDER_BACKEND", "") or "").strip())
    status = "payment_provider_not_configured" if not configured else "payment_provider_integration_incomplete"
    return {
        "provider_configured": configured,
        "provider_ready": False,
        "status": status,
        "capabilities": {
            "individual_checkout": False,
            "verified_payment_webhooks": False,
            "renewal_management": False,
            "refund_processing": False,
        },
    }
