# Activities 13–14: Teacher Studio and Learning Administration Centre

**Status:** Implemented in the isolated Personalized Learning source copy. Not deployed and not migrated in any production environment. Activity 9 catalogue publication remains hard-disabled.

## Activity 13 — Teacher Learning Studio

A lazy-loaded teacher-only dashboard is available as **Learning Studio** in the existing teacher dashboard. It provides a text/catalogue-only discovery view of currently eligible, reviewed, published **Free** resources and learning programmes from the shared catalogue and the teacher's own school. Catalogue lists and details recheck rights, publication/review state, age and school scope; staff-facing views do not include file download URLs/private asset keys or premium material.

Teachers may create, edit and submit only their own school resource/path drafts. Draft and changes-requested states are editable; submitted items enter the full-school-admin review queue. Source/provenance, licence or rights notes, attribution, language, age, and review requirements remain controlled by the existing content-governance API. The UI does not publish content, create shared catalogue records, import external content, attach files, or generate text automatically.

Teachers can recommend one current, visible, published Free resource or programme to an active, consent-eligible learner enrolled in a stream assigned to that teacher. The endpoint rejects out-of-scope learners and hidden, unreviewed, unpublished, retired, age-ineligible, premium, and cross-school items. Each recommendation is explicitly teacher-selected and tagged as such; it is not Activity 15's deterministic recommendation algorithm and does not use marks, exams, attendance, reports, fees, risk indicators, or other academic/financial data. Learners receive an inbox in their existing learner shell and can keep or dismiss recommendations; their actions are owner-scoped and audited.

Teacher learning summaries include only learning participation counts and last learning activity for students in currently assigned streams. The new list omits DOB, age band and account status. No assessment results, attendance, report-card data, fees, raw prompts, or private learner work are queried or returned. The school-controlled Teacher Studio switch also blocks the older single-learner learning-summary endpoint.

## Activity 14 — Learning Administration Centre

A separate lazy-loaded **Learning Centre** tab is available only to an active, single-role full school administrator. School administrators can inspect school learning aggregates, manage learning settings, review submitted school resources/programmes/translations, and see approved/published programme lifecycle counts. The review UI shows the school-submitted text and translation metadata and offers the existing approve/request-changes decisions. Approval does not publish content.

A school has one optional `LearningSchoolSettings` row. Until an administrator saves settings, the API returns these defaults without creating a row:

- School-managed learning access: enabled.
- Teacher Learning Studio: enabled.
- Teacher recommendations: disabled.
- Additional school learner-age interval: 0–120.

The age interval is an additional school-level gate. The exact roster DOB is evaluated server-side; it is not returned by these settings. Bounds are constrained at the API and database levels and cannot override or widen Marian's age verification, guardian-consent, account-status, school-suspension, resource-age, licence, language, tenant, publication, or subscription controls. Turning learning access off blocks protected learner flows; turning the Teacher Studio off also blocks teacher authoring and both teacher progress-summary APIs. Turning recommendations off blocks new recommendations. School administrators see school aggregate usage only through this Centre; it does not list independent public learners or their records. Deputies, teachers, Django staff/superusers, and conflicting teacher/admin identities cannot manage these controls.

Settings reads/updates, school-level aggregate reads, review-queue reads, teacher learner-list reads, resource/path detail reads, recommendation creation, and learner recommendation responses have minimal audit records. Review-queue audit metadata contains only counts by submitted content type; translated text, titles, DOB, marks and learner prompts are not copied into its audit details.

## API surface

All new endpoints are under `/api/learning/v1/` and use existing Marian authentication, suspension checks, throttles, tenant models and learning audit events.

| Route | Purpose |
|---|---|
| `GET teachers/learners/` | Assignment/stream-filtered active eligible learner summaries for the authenticated teacher. |
| `GET teachers/catalog/topics/` | Active learning topics. |
| `GET teachers/catalog/resources/`, `GET teachers/catalog/resources/<id>/` | Free, currently visible resource discovery and detail. |
| `GET teachers/catalog/paths/`, `GET teachers/catalog/paths/<id>/` | Free, currently visible programme discovery and detail. |
| `POST teachers/learners/<student_id>/recommendations/` | Recommend exactly one `resource_id` or `path_id` plus an optional bounded explanation. |
| `GET recommendations/`, `POST recommendations/<id>/response/` | Learner's own currently visible recommendations and accept/dismiss action. |
| `GET/PATCH admin/learning-settings/` | Full-school-admin-only settings read/update. |
| `GET admin/learning-summary/` and existing `/studio/review-queue/` | Existing school aggregate and tenant-scoped review queue; the latter now audits aggregate read counts. |

## Migrations and deployment

Two additive learning migrations were added:

- `learning.0008_learningschoolsettings` creates the one-row-per-school settings table.
- `learning.0009_learningschoolsettings_learn_school_age_min_plausible` adds the minimum-age plausibility database constraint.

Django's test runner applied these migrations to a disposable SQLite test database only. No application or production database was migrated. Before a deployment, operators should review both migrations, take and verify the normal Marian database backup, apply them through the reviewed release process, and run the migration checks against the intended PostgreSQL-like database. No credentials or provider configuration is required for these features.

Do not enable learning publication based on these activities. The code still hard-blocks publication (`content_publication_policy_unapproved`, HTTP 503) until the separate licence/rights, moderation and shared-catalogue ownership decisions are approved. The optional durable private-file/scanner configuration and the skipped row-lock concurrency checks also remain separate rollout gates documented elsewhere in the roadmap.

## Verification run

Run from the project copy's `backend/` with `DJANGO_DEBUG=True` and production database variables unset:

- `python manage.py check` — passed with no system-check issues.
- `python manage.py makemigrations --check --dry-run` — passed; no model/migration drift.
- `python -m compileall -q learning schools api` — passed.
- `python manage.py test learning.test_staff_learning_api learning.test_content_api --verbosity=1` — 24 tests passed; one existing SQLite-only lock/concurrency case skipped.
- Full backend suite `python manage.py test --verbosity=1` — **1,270 tests; 1,268 passed, 2 skipped**. The two skips are row-lock/concurrency tests because SQLite does not implement `SELECT FOR UPDATE`; execute those on the intended PostgreSQL-like test backend before deployment.
- Frontend `npm test` — **15 passed, 0 failed**.
- Frontend `npm run build` — passed. The new staff screens are lazy-loaded; the main dashboard bundle is below Vite's 500 kB warning threshold.
- Frontend `npm run lint` — **0 errors and 78 warnings**, unchanged from the pre-Activity-13/14 project baseline; no warnings were reported in the new screens.

Existing test-environment warnings about missing collected `staticfiles/`, the short development JWT key, simulated backup/SMS outcomes and EOF markers are non-failing environment messages. Tests do not certify a live deployment, a production database migration, operational content publishing, or PostgreSQL lock behavior.
