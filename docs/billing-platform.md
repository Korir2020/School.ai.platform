# Marian platform billing and licensing

## Scope and privilege boundaries

The **Billing Centre** is school-account billing, not the learner fee module. It exposes only the signed-in full school administrator's own account. Deputies, bursars, teachers and parents do not receive that screen or its API privilege. Platform configuration, all-school summaries, invoice issuance, school entitlement changes, settlement verification and billing audit review are restricted to Django superusers (the platform Super Administrator role). School-supplied invoice/payment references never grant an entitlement.

## Trials and academic data

New school records receive a free trial with no calendar end date. Older schools are backfilled as `unconfigured`; the migration does not silently grant those tenants a trial or a paid entitlement. The first trial cycle is based on active enrolments captured when the first exam is created. Evidence is recorded from persisted exams/results, actual report analytics generation and immutable published report-card artifacts. Publication can recover a missed first-exam creation hook, and best-effort evidence failures are logged without blocking academic workflows. Completion requires published results covering every active learner in each captured class, analytics for each class, and archived report cards for each eligible learner. A duplicate event is idempotent. After completion, another exam cycle is blocked until a paid entitlement is verified or the account is explicitly managed by a platform Super Administrator. The original examination calculations, publication logic, archived report bytes, and historical learner/fee data are not rewritten.

## Price assumptions

Default values are editable by the platform Super Administrator and are commercial assumptions, not confirmed legal, tax, or provider terms. Termly price is the greater of the minimum and active enrolled headcount multiplied by the per-student term rate. Annual price applies the configured annual discount to configured terms per year. A Marian cloud perpetual licence is an upfront multiple of the annual price; its later cloud service renewal is separately priced. VAT is `undecided` by default and no tax advice is implied. School-hosted perpetual deployment and maintenance are intentionally unavailable as production-ready offerings until an installer, independent upgrade process, school-only backup/recovery path, and support/maintenance terms have been approved.

## Payments are not live

School admins can request server-priced invoices and submit bank-transfer references. These remain pending. Only a platform Super Administrator who has checked cleared funds may verify one; verified payments are linked to the invoice and entitlement and recorded in the audit log. M-Pesa, card, and automated settlement are not enabled until a provider is approved, credentials and callback signing secret are provisioned, and an integration has been tested. `BILLING_WEBHOOK_SECRET` must be at least 32 characters before the signed callback endpoint accepts events; it must be stored as a production secret, rotated securely, and never committed to source control. Callback events are HMAC-verified and idempotent; transaction amount, currency, invoice, transaction ID, and replayed event payload are checked. Reversal callbacks cancel/revoke the entitlement attached to the reversed invoice and set school status to payment pending. This does not alter academic records.

## Expiry and deployment operations

`python manage.py expire_billing` materializes elapsed subscription/service statuses. Schedule it daily in the deployment environment. Exam-write entitlement checks also compute subscription and cloud-service expiry on every request, so command scheduling lag cannot extend access. Post-expiry restrictions are inactive unless a platform Super Administrator explicitly approves a selected policy; historical reads and stored artifacts remain preserved. A cloud perpetual licence does not lose its perpetual software licence when its separate cloud-service period ends; any restrictions require explicit approved post-expiry policy.

## Migration and verification

Run `python manage.py migrate` after backup and the normal staged deployment review. The billing migration creates billing-specific tables and backfills missing profiles only as `unconfigured`; it does not update legacy academic records. Before rollout, verify backups, account-to-school mapping, pricing assumptions, VAT treatment, the application's real Django `is_superuser` assignment policy, callback secrets/provider approval, school support terms, and expiry-policy decisions. Test results should include both billing-specific tests and the existing school/API tests. Rollback should use the platform's normal database backup/restore procedure; do not drop billing tables or reverse the backfill blindly.
