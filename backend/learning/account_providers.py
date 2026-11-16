"""Provider-neutral contracts for Activity 11 account operations.

No email/SMS/identity provider adapter is included in this project copy. The
contract is intentionally descriptive: a configured Django email or SMS
backend is not treated as verified delivery, and this module never sends a
message or verifies a person.
"""

from typing import Protocol

from django.conf import settings


CAPABILITY_NAMES = (
    "independent_registration",
    "email_verification",
    "sms_verification",
    "age_verification",
    "guardian_identity_verification",
    "guardian_consent_capture",
    "invitation_delivery",
    "account_recovery",
)


class LearningAccountProvider(Protocol):
    """Interface required of a future real, server-side account provider."""

    def is_ready(self) -> bool: ...

    def capabilities(self) -> dict[str, bool]: ...

    def send_contact_verification(self, *, channel: str, destination: str, code: str) -> object: ...

    def verify_contact_code(self, *, challenge_id: str, code: str) -> bool: ...

    def verify_age(self, *, subject_reference: str, evidence: object) -> bool: ...

    def verify_guardian(self, *, subject_reference: str, guardian_evidence: object) -> bool: ...

    def deliver_invitation(self, *, destination: str, token: str, expires_at: object) -> object: ...

    def deliver_recovery(self, *, destination: str, recovery_url: str) -> object: ...


def provider_configuration_state():
    """Describe configuration truthfully without exposing import paths or secrets.

    Provider code is not loaded or trusted merely because a setting is present.
    The registration, consent, delivery, and recovery orchestration is not yet
    connected to a real adapter, so every dependent capability remains false.
    """
    configured = bool(str(getattr(settings, "LEARNING_ACCOUNT_PROVIDER_BACKEND", "") or "").strip())
    reason = "provider_not_configured" if not configured else "provider_adapter_integration_incomplete"
    return {
        "provider_configured": configured,
        "provider_ready": False,
        "status": reason,
        "capabilities": {name: False for name in CAPABILITY_NAMES},
    }
