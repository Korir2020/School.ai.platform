# Activity 20 — Release readiness and operational verification

**Status: LOCAL TECHNICAL VERIFICATION PASSED; PRODUCTION RELEASE GATES REMAIN OPEN.**

This report records verification in the independent source copy only. No production database was contacted, migrated, backed up, or modified. No AI, payment, email/SMS, or other provider credential was forwarded to any test subprocess.

## Reproducible local verification

Run from the project root:

```bash
python3 scripts/sqlite_backup_restore_rehearsal.py
python3 scripts/release_readiness.py
```

The release runner creates a temporary directory and points only Django's **test-only SQLite database** to it. It invokes child processes with an explicit minimal environment allowlist rather than inheriting arbitrary environment variables. Database DSNs/passwords, provider credentials, external tool injection variables, and the caller's Django secret are not forwarded; local verification uses a non-production secret, `DEBUG=True`, and test-only hosts. The `MARIAN_TEST_SQLITE_PATH` setting is honored only while Django runs `manage.py test` in the SQLite development backend. It does not change normal application database selection or PostgreSQL production settings. Unit tests prove that this environment filter removes database/provider credentials.

The final runner completed successfully: credential-isolation tests **2/2 passed**; Django system checks and migration-drift verification passed; Activity 18–19 focused tests **3/3 passed**; the full learning-domain suite discovered **195 tests, 193 passed and 2 SQLite row-lock tests skipped**; the disposable SQLite backup/restore rehearsal passed; frontend tests **18/18 passed**; frontend lint **0 errors and 79 project warnings**; Vite production build passed. The two skipped row-lock tests need a database supporting `SELECT FOR UPDATE`, such as an isolated PostgreSQL environment.

Separately, the complete Marian backend suite discovered **1,291 tests, 1,289 passed and the same 2 tests skipped**. The new Activity 17 quiz/content-governance tests discovered **27 tests, 26 passed and 1 skipped** when run alone with their content-governance suite. No production database migration was run. Existing non-failing output includes the project’s missing collected `staticfiles/` notice and test-only simulated provider/backup messages. Lint and build continue to show pre-existing warnings, with no new warnings in the changed quiz components.

The disposable SQLite rehearsal proves only that the local rehearsal script works. It is not evidence of an approved production backup provider, encrypted off-site storage, or a production restore.

## Remaining release gates

### PostgreSQL and concurrency

Run all relevant backend tests, especially the two `SELECT FOR UPDATE` cases, against an isolated PostgreSQL test database matching the intended deployment. Do not point a test suite at production.

### Backup, restore, rollback, and forward-fix

Production evidence still requires an owner-approved PostgreSQL backup provider, encrypted backup storage, restore credentials, retention rules, an isolated restore target, and an exercised rollback/forward-fix runbook. No production backup or restore was attempted.

### Storage and malware scanning

Activities 8–10 remain provider-gated. A durable private object-storage backend, private bucket policy, malware scanner, quarantine monitoring, failed-scan handling, deletion retry, and retention/purge schedule must be selected and configured. Until then production uploads remain fail-closed/quarantined.

### Account, guardian, email/SMS, payments, and AI

Activity 11's existing-student access path still needs to avoid redundant invitations where a trusted server-side roster/account relationship exists. Real age/contact verification, guardian identity/consent, provider-backed invitation/recovery delivery, pricing/entitlements, verified payment events and settlement reconciliation are not live. Activity 16 AI remains disabled until provider approval, privacy/retention, child-safety, moderation/escalation, and budget policies are approved and real credentials are configured.

### Catalogue and offline policy

Activity 9 publication remains hard-gated pending licensing/rights allowlists, moderation standards, shared-catalogue ownership, and human review of important Kiswahili translations. Activity 19 offline packages must not be enabled for content without approved rights and retention policy. Device-revocation operations and service-worker/content-delivery verification remain required before production enablement.

### Activity 17 practice quiz and retention

The first server-scored, non-AI multiple-choice quiz slice is implemented, but does not complete the Interactive Learning Studio. Quiz attempts are private and do not expose scores to teachers; the owner still needs to approve retention/access policy for quiz outcome records before production use. No quiz becomes learner-visible while the existing publication gate is closed.

### Mobile, accessibility, analytics, and incidents

Automated UI/build checks and responsive source review are complete for this source copy. A real Android/iOS device pass, screen-reader checks, keyboard-only navigation, reduced-motion checks, network interruption, expiry, revocation, and reconnect/sync checks remain required before release. Activity 18 analytics retention/deletion and incident-response evidence also need owner approval and operational exercise.

## Release decision

This source copy is **not certified or deployed for production**. It is ready for an owner-controlled staging verification pass. Remaining items require infrastructure, policy, provider credentials, production-like PostgreSQL, or real-device/operator approval; they are not implementation claims to fill silently.