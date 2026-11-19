# Marian — Changelog

## 2026-11-20
### Content Studio Stages 2 to 7 (feature branch, not merged to main)
- Stage 2: licence source types, expiry and verifier fields, with evidence checks at submit (migration 0014).
- Stage 3: duplicate a resource with a parent link; approval stamps the licence verifier (0015).
- Stage 4: superuser-only curator revoke endpoint, audited.
- Stage 5: takedown with a required reason and audit fields (0016); allowlisted YouTube embed URL.
- Stage 6: question bank - new `LearningQuestion` table (0017), existing quizzes copied in by 0018, and `learning/question_lookup.py`, which never returns answers.
- Stage 7: curator review screen, duplicate and takedown screens, licence fields on the resource form, version history, and a restore endpoint with an Earlier versions list in the teacher form. Restore creates a new version and never edits an old one. A Learning tab was added to the teacher, school admin and superadmin dashboards.
- Publication gate unchanged: `PUBLICATION_POLICY_APPROVED` is False, so nothing reaches learners. Learning tests: 259, OK, 2 skipped. Full backend: 1368, OK, 9 skipped. Frontend: 22 passing.

## 2026-11-19
### Content Studio Stage 1 (feature branch, not merged to main)
- Added Marian author and curator roles (`LearningContentRole`, migration 0013). Only a superuser grants a role and each grant is audit-logged; superuser and staff get no implied authority.
- Added platform-wide content authoring and curator-only review in `platform_api.py`. Authors cannot review their own work and drafts are visible only to their author.
- Added a licence check at submit: CC BY-NC and CC BY-ND rejected, other licences need a recorded permission note.
- Publication gate unchanged: publish still returns 503. Learning tests: 208, OK, 2 skipped.

## 2026-11-15
### Platform billing and licensing foundation
- Added tenant-scoped school billing profiles, subscriptions, cloud perpetual licences, invoices, payments, population snapshots, capacity requests, genuine trial-cycle evidence and audit events.
- Added role-separated Billing Centre screens and APIs: full school admins see only their own platform billing; Django Super Administrators control pricing, tenant status, invoices and settlement review.
- New schools receive a no-calendar-expiry trial; pre-existing schools are migrated as unconfigured. Trial completion requires published genuine cohort results, analytics and archived reports.
- Bank-transfer references stay pending until human settlement verification; signed callbacks remain disabled without provider approval and a 32-character secret. School-hosted deployment is not represented as production-ready.
- Exam-cycle write gates, `expire_billing` command, idempotency, manual audit notes and billing-specific tests added. Existing marks, calculations, publications, report archives and learner-fee workflows are preserved.

## 2026-11-12
### Migration Centre (learner list import)
- Upload a register (Excel, CSV, TSV or typed PDF) or paste the table; nothing is saved until the administrator confirms.
- Column recognition covers common headings, including Swahili (Namba ya Kuingia, Jina Kamili, Darasa); unknown headings are matched by hand, one column at a time.
- Rows are classified as ready, needs confirmation, needs fixing, already in Marian or skipped, with a reason in plain language on every row.
- Fixes and decisions live in the import only: the original file is never changed. Corrections can be made per row or for the whole selection, and a class can be chosen once for a file with no class column.
- Grade 10-12 learners need an assessment number before they can be imported; a learner without an admission number gets a marked temporary one.
- Repeating an import never adds a learner twice: admission numbers and names are checked against Marian and against the file itself.
- Import is idempotent per request id, and the whole commit is one transaction with an audit entry (school, user, counts, classes, temporary numbers).
- api/migration_rules.py, api/migration_check.py, api/migration_commit.py, frontend/src/MigrationCentre.jsx, frontend/src/migration.css, tests in api/test_migration_*.py

## 2026-09-22

### Project Started
- Created the GitHub repository.
- Created PROJECT_CONTEXT.md.
- Created ARCHITECTURE.md.
- Created DECISIONS.md.
- Established the initial project vision and architecture.

## B4 - Setup wizard backend
- GET /api/setup/ (checklist: profile, academic year, term, stream, subject)
- POST /api/setup/complete/ (full admins only, atomic, audited, idempotent)
- /api/auth/me/ now returns setup_complete
- api/setup_views.py, api/test_setup.py
