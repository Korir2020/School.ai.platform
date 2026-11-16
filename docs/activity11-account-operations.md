# Activity 11 — Account and Guardian Operations

**Implementation status: partial and dependency-gated.** This document describes the implementation in this independent Marian source copy. It is not a production deployment or provider-integration approval.

## Approved age and guardian rules

The approved policy is implemented centrally in `backend/learning/account_policy.py` and enforced by learner permissions, school claims, catalogue age checks, and registration status responses:

- Below age 10: no independent public registration; access is school-managed only with the required safeguards.
- Ages 10–17: independent access requires verified guardian involvement and consent.
- Age 18 and above: independent self-registration is allowed only after real verification is available.
- Unknown age: deny protected learning features until age is established and verified. Guardian approval of a school invitation is not age verification.
- The independent-registration minimum defaults to 10. `LEARNING_MIN_INDEPENDENT_AGE` may be configured only from 10 through 17; values below the approved minimum are rejected.

School-linked age is derived from the linked Marian roster date of birth and the account's age band must match the official roster. Independent public age/contact/guardian verification is provider-dependent and has not been implemented. No exact date of birth is returned by the learning APIs added here.

## What is implemented

- Activity 11 account state and verification metadata in the learning domain, with additive migration `learning.0005_learninginvitation_delivery_status_and_more` and conservative normalization of legacy age bands.
- Existing Marian authentication and school-role records remain authoritative. No second credential system was introduced.
- Provider-neutral account provider contract and public capability report. Blank provider configuration is the default; setting a provider module path alone never makes it ready or enables any provider capability.
- Public independent-registration endpoint returns HTTP 503, creates no user/profile, and collects no registration evidence until complete real provider workflows are integrated.
- Existing school invitation, guardian approval, and claim path remain. Tokens are one-time and stored hashed. Full school administrators can issue/revoke invitations from the account screen, see an issued code once for secure manual handoff, and inspect status; no delivery is simulated. Linked guardians can review and approve only pending invitations for their linked students. Learners can claim a school code through the public claim form, then use Marian's existing sign-in. Unknown-age claims remain Marian-authenticated but cannot use protected learning features. An expired open invitation is transactionally retired before a fresh one-time invitation is issued; the old token stays unusable.
- Guardian summaries are limited to linked learners and omit learning-progress counts for ineligible, consent-withdrawn, or inactive accounts. A linked guardian may withdraw consent; protected access is blocked, and the action is audited.
- Learners can request suspension/deletion and cancel a pending request. Requests restrict learning access, but do not hard-delete accounts, student records, or learning history.
- Assigned teachers can read minimal progress summaries for eligible active learners in their assigned streams; conversation text is not returned. Full school administrators receive school-scoped aggregates and a bounded list of school-linked learning accounts, with audit events and suspension/reactivation controls. Independent public learners are excluded from school admin queries.
- Responsive public status and school-invitation claim, learner lifecycle, guardian-linked learner/pending-approval, and school-admin summary/list/state/invitation-management screens are integrated through Marian's existing public screen switcher and role tabs. The status screen explicitly says independent registration is unavailable. The invitation delivery-status action is check-only and reports that no message was sent. School invitation and guardian invitation list reads are audited and capped; response payloads omit DOBs and token hashes.

## Activity 11 routes

All routes use `/api/learning/v1/` as the prefix. Existing Marian authentication is reused where authentication is required.

| Route | Access and current behavior |
| --- | --- |
| `GET accounts/capabilities/` | Public, truthful capability state; never exposes credentials. All provider-dependent capabilities are false until a real adapter and orchestration are integrated. |
| `POST accounts/register/` | Public, throttled, always 503; no account is created and no verification is simulated. |
| `GET/POST account/lifecycle-requests/` | Authenticated user lists own requests or submits a suspension/deletion request for an eligible own/linked account. Submission restricts protected learning access; no destructive deletion occurs. |
| `POST account/lifecycle-requests/{id}/cancel/` | Requesting user may cancel their own pending request; prior account state is restored where eligible. |
| `GET guardians/learners/` | Authenticated linked Marian guardians receive minimal linked-learner summaries; sensitive reads are audited. |
| `GET guardians/invitations/` | Linked guardians receive at most 100 unexpired pending school invitations only for their linked active students; reads are audited. |
| `POST invitations/{invitation_id}/guardian-approval/` | Linked Marian guardian records approval only for a pending invitation belonging to one of their own linked students; school suspension, expiry, and single-approval checks apply. The guardian action is audited. |
| `POST guardians/learners/{profile_id}/consent/withdraw/` | Linked guardian withdraws consent; protected learning access is blocked and the action is audited. A new verified consent grant is not available in this copy. |
| `GET teachers/learners/{student_id}/summary/` | Assigned Marian teachers receive minimal progress aggregates only for an active assigned learner who passes the same eligibility gate. |
| `GET admin/learning-summary/` | Full active school administrator receives only their school's aggregate learning summary. |
| `GET admin/learning-accounts/` | Full active school administrator receives at most 200 own-school student names, age bands, consent states, and account states; no DOBs, admission numbers, passwords, or public accounts. `truncated` identifies a capped response. Read is audited. |
| `POST admin/learning-accounts/{profile_id}/state/` | Full school administrator may suspend/reactivate an own-school learning profile; state changes are audited. Existing age/consent checks still apply after reactivation. |
| `GET admin/invitation-candidates/` | Full active school administrator receives at most 200 active, own-school roster candidates without a learning account or unexpired open invitation. Only ID, name, age band, guardian-required flag, and guardian-availability boolean are returned; no DOB or guardian identity is exposed. Reads are audited and `truncated` identifies a capped response. |
| `GET/POST admin/invitations/`, `POST admin/invitations/{id}/revoke/` | Existing full-admin, own-school invitation listing/creation/revocation. Invitation and candidate list reads are audited. Raw claim code is returned once at creation for manual secure handoff; the screen displays it only in the creation response, it is not sent by Marian, and it cannot be retrieved from a list. Expired unclaimed records are retired safely when an administrator issues a fresh invitation. |
| `POST admin/invitations/{id}/resend/` | If the invitation remains active, returns 503 with delivery status; sends no email/SMS, does not change the token, and records an audit event. Expired/revoked/claimed invitation returns 409. |
| `POST invitations/claim/` | Public, throttled one-time school-code claim using Marian's existing account model and password validators. A minor's linked-guardian approval is rechecked server-side; unknown age remains blocked from protected learning features. The public page does not enable independent registration. |

## Marian authentication and password recovery

The existing Marian login and password-recovery routes were inspected and left unchanged. Existing password recovery retains its generic response for known/unknown identifiers, active-account and eligible-email checks, cooldown/rate limiting, expiring single-use reset tokens, password validation, session/token invalidation, and audit events. Existing recovery behavior is not replaced or duplicated by Activity 11.

Provider-backed independent-account recovery, guardian-assisted recovery, and school-assisted learner recovery are not implemented. The UI must not present those flows as available. Existing Marian password recovery remains subject to its current email-backend and account-eligibility configuration.

## Configuration and rollout

The reference environment settings are in `backend/.env.activity11.example`:

```dotenv
LEARNING_MIN_INDEPENDENT_AGE=10
LEARNING_ACCOUNT_PROVIDER_BACKEND=
LEARNING_ACCOUNT_RETENTION_DAYS=
```

- Preserve `10` as the default minimum. Changing the value cannot lower it.
- Keep provider configuration blank until the service is approved, integrated, and independently tested. A nonblank path does not switch capabilities on.
- `LEARNING_ACCOUNT_RETENTION_DAYS` is informational only. No scheduled retention or purge worker exists, and no permanent deletion executes.
- Before any production schema change: back up the target, review the additive migration, confirm production database variables and deployment credentials explicitly, then follow the deployment's normal migration/change-control procedure. This work has not migrated a production database.

## Explicitly incomplete / release gates

Activity 11 remains **partial**. The following capabilities are not implemented and must remain disabled: real email/SMS delivery and verification, independent registration, age/identity verification provider adapters, verified guardian identity and new-consent capture, automated invitation delivery, provider-backed recovery, guardian-/school-assisted recovery orchestration, automated retention/deletion, assigned-case moderator access, and provider operational monitoring. The provider protocol and configuration status are only a foundation; they are not end-to-end integrations.

The lifecycle API records a non-destructive request and changes learning access; it does not perform legal deletion or retention enforcement. No password or private AI conversation is available to school administrators. Existing Marian staff/superadmin privileges do not implicitly grant the full-school-admin learning permission. PostgreSQL-like testing of row-lock/concurrency behavior remains a production-readiness requirement.

## Verification status

The final validation run is recorded in [`personalized-learning-implementation-status.md`](personalized-learning-implementation-status.md): focused Activity 11/role checks **81/81 passed**; full Marian suite **1,251 discovered, 1,249 passed, 2 skipped**; frontend **10/10 tests passed**, Vite production build passed, and lint completed with zero errors (78 warnings). Python compilation, Django system checks, and migration-drift checks passed. Production database variables were unset and no production migration or deployment occurred. The two skipped cases require a PostgreSQL-like database for row-lock/concurrency verification; clean ZIP integrity/hash is recorded in the final handoff.


## Independent learner profiles and individual subscriptions

**Status: safe foundation implemented; independent signup and paid activation are not operational.** This section records the independent-first product decision for this source copy. It does not enable registration, checkout, premium entitlements, or production deployment.

### Account and data boundaries

- Personalized Learning uses Marian's existing authentication. An independent learner profile is a separate learning-domain record and is not automatically matched or linked to a school/student using a name, email, or other weak identifier. No future school link for teacher recommendations is exposed in this version.
- School-managed learner profiles and workflows remain distinct and continue to use the Marian roster, school invitations, and linked guardian relationship. Independent learner data is excluded from school-admin learning summaries and lists. Existing school staff/teacher access remains limited to its separately authorized, minimal progress summaries; private AI conversation access is not added.
- Public independent registration remains disabled (HTTP 503). No independent user/profile, age-verification result, guardian-verification result, or consent record is created by the unavailable registration flow. Existing Marian sign-in and password recovery are unchanged.
- The approved age policy still applies: under 10 is school-managed only; ages 10–17 require verified guardian involvement and consent for independent access; adults require real age/contact verification; unknown age cannot access protected learning features. These independent verification integrations are not implemented, so the policy must not be treated as completed verification.

### Separate individual plan and billing rules

Personalized Learning is an individually paid add-on, not a school fee. Individual subscription models and endpoints do not create, read, or update `StudentFee` or `FeePayment` records. A school subscription or fee payment does not confer individual Premium access.

Migration `learning.0006_individual_subscription_access_tiers` adds resource/path access tiers and separate individual plan, subscription, and provider-transaction records. Migration `learning.0007_seed_individual_learning_plans` seeds an active Free plan and an inactive Premium plan. Premium has no configured price, currency, recurring interval, or entitlements; no price or feature promise is inferred. Product/owner approval is required before configuring Premium pricing, billing interval, currency, and included entitlements.

Premium access is enforced by backend catalogue/resource/path, asset-delivery, activity, saved-item, and goal checks. An account defaults to Free unless the backend finds an eligible active profile, an active Premium subscription within its current period, and a succeeded transaction with provider-verification timestamp/IDs and amount/currency matching the configured plan. Missing, unpaid, expired, or unverified payment falls back to Free. Client flags and plan display do not grant access.

### Subscription routes

All routes use `/api/learning/v1/`. Public plan/capability responses contain product configuration only; learner status/history are scoped to the authenticated learner or an authorized linked guardian. Sensitive history reads create an audit event.

| Route | Access and current behavior |
| --- | --- |
| `GET subscriptions/plans/` | Public; returns configured plan metadata. The seeded Premium plan is inactive and unpriced. |
| `GET subscriptions/capabilities/` | Public; reports separate billing, disabled registration, provider readiness, and checkout status without learner data. |
| `GET subscriptions/me/` | Authenticated Marian user; returns only that user's linked learning profile entitlement. A missing profile returns 404. |
| `GET subscriptions/history/?profile_id=...` | Authenticated learner or authorized linked guardian; bounded history with provider-verification indicator and an audit record. It does not expose provider secrets. |
| `POST subscriptions/checkout/` | Authenticated, eligible profile owner or permitted linked guardian. Currently returns HTTP 503, `payment_created: false`, and `premium_activated: false`; it creates no checkout, transaction, or subscription record. Unsupported request fields are rejected. |

### Explicit operational blockers

- **Payments:** no real payment-provider adapter, signed/verified webhook, refund/reconciliation flow, idempotent provider event processing, or independently validated settlement path is integrated. A provider setting by itself cannot switch readiness on. No charge or success is simulated.
- **Age/contact and guardian verification:** no independent age/contact verification provider, independent guardian-identity verification, or new guardian-consent capture/grant workflow is integrated. The existing school-linked invitation/guardian workflow is not a substitute for independent signup verification.
- **Signup and account recovery:** independent signup remains disabled until those real verification workflows and protected account-recovery paths are implemented and tested. Signup must not be represented as available.
- **Premium commercialization:** Premium remains inactive until a price, currency, monthly/yearly interval, and entitlements are explicitly approved and configured. Checkout still cannot operate until the actual provider adapter and verified event handling exist.
- **Future school link:** teacher recommendations through linking an independent learner to a school are deferred to a separately designed, consented, auditable workflow. No automatic roster matching is implemented.
- **AI tutoring:** there is no AI tutoring endpoint in this source copy; the free plan's AI request limit is zero and no plan advertises AI tutoring as available.

The frontend status and learner account screens display the unavailable signup/checkout state and separate billing model. Migrations have been applied only to disposable test databases in the validation described in the implementation-status report. No production database migration or deployment was performed.
