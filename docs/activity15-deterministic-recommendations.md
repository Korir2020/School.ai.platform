# Canonical Activity 15 — Explainable Deterministic Recommendations

**Status:** Implemented in this independent source copy on 16 November 2026. **This completes Activity 15 only; it does not mean the overall Personalized Learning product or release is complete.** See `personalized-learning-canonical-roadmap.md` for the single current activity sequence and all remaining work.

## What was implemented

- Added `POST /api/learning/v1/recommendations/generate/`, a deterministic server-side rules engine separate from the existing teacher-selected recommendation workflow.
- The engine considers only the signed-in learner’s own selected topics, active learner-set goals, preferred formats/difficulty/language, and recent target identities from learner-owned `started`, `progress`, and `feedback` events. It never reads event details, client-supplied profile/target IDs, event duration, marks, exams, report cards, attendance, school fees, risk scores, AI prompts, or demographic profiles.
- Candidate resources and paths are rechecked against current publication/review state, age bounds, language/approved resource translations, school/public scope, suspension rules, path-item visibility, and the shared subscription entitlement policy. Premium catalogue items are considered only if the authenticated learner currently passes the active premium entitlement check. A pricing or payment response cannot activate that entitlement through this feature.
- Signal codes are allowlisted: `interest_match`, `goal_path_match`, `goal_topic_match`, `recent_topic_activity`, `format_match`, `difficulty_match`, `language_match`, and the neutral `catalog_starter`. Explanations are provided in English or Kiswahili and are generated from codes, not free-text profiling.
- Work is bounded to 160 resources, 80 paths, 80 recent events, and at most eight active automatic suggestions per learner. Suggestions expire after 30 days. Generation is rate-limited to 30 requests per hour outside tests; the model has partial unique constraints against duplicate active automatic suggestions for the same learner and target.
- Added safe generation audit events containing only enabled state, counts, and algorithm version—not topic selections, target IDs, event contents, or learner work. The existing read/respond audit events remain in place.
- Existing teacher-selected recommendations remain a separate source. The learner can pause automatic personalization without hiding teacher-selected suggestions, inspect why an item appears, accept/keep it, dismiss it, edit their topic/format/difficulty inputs, and manually refresh suggestions. A dismissed target is not resurfaced by the automatic engine.
- Added an English/Kiswahili mobile-responsive preference panel and testable frontend preference helpers. Topic selections are capped at ten in the UI; API validation and catalogue visibility remain authoritative.
- Added migration `learning.0011_learningrecommendation_learn_auto_reco_res_active_and_more` for additive uniqueness protection. Existing school-management, academic, billing, Migration Centre, archived reports, and previous learning functionality were not rewritten or modified by this activity.

## Explicit non-goals and remaining dependencies

This is a deterministic recommendation service, not AI. It does not tutor, generate or translate content, or provide exercises. No AI provider was configured or called. It does not guarantee results when no currently eligible, reviewed content exists; shared-catalogue publication is still policy-gated by Activity 9. Activity 16 (AI gateway) and Activity 17 (interactive/project studio) remain unimplemented. Free learning availability still depends on rights-approved and published content. Premium payment processing and activation remain non-live and separate from school subscriptions and fee accounts.

The latest confirmed product decision is that an active Marian student should gain Personalized Learning through the existing eligible Marian account without a redundant second invitation. The current Activity 11 account-linking path remains invitation/claim-based in some cases, so it still must be updated and verified before this new access policy is fulfilled. Independent registration, provider-backed age/contact/guardian verification, guardian-as-payer, and configurable pricing operations remain incomplete or disabled. Do not tell users those integrations are live.

## Verification in the isolated source copy

- `python -m py_compile` for the changed backend modules — passed.
- `DJANGO_DEBUG=True python manage.py check` — passed; no system-check issues.
- `DJANGO_DEBUG=True python manage.py makemigrations --check --dry-run` — passed; no migration drift.
- Focused recommendation API tests — **6 passed**. Coverage includes selected interests/goals/preferences/recent activity, Kiswahili explanation, age/tenant/review/entitlement filtering, idempotent refresh, dismissed-item suppression, opt-out, role denial, rejected client-supplied targets, and audit-signal sanitization.
- Full learning-domain suite — **183 tests: 181 passed, 2 skipped** (the existing SQLite `SELECT FOR UPDATE` concurrency cases require PostgreSQL-like verification).
- Final full Marian backend suite — **1,279 tests: 1,277 passed, 2 skipped**. The skipped tests are the SQLite row-lock/concurrency cases; rerun them on production-like PostgreSQL before production deployment.
- Frontend Node tests — **18 passed, 0 failed**; the new unit tests cover preference normalization, the ten-topic cap, and format/difficulty allowlists.
- Frontend lint — **0 errors and 79 warnings**. No Activity 15 component/helper diagnostic was reported; the warnings include existing project-wide React/unused-variable warnings.
- Vite production build — passed. It still reports the existing >500 kB minified chunk warning.

All tests ran in this independent copy using disposable test databases. No production database was migrated, no external AI or payment provider was contacted, no content was published, and no live deployment was performed.
