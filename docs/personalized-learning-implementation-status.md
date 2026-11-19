# Personalized Learning Implementation Status

> **Numbering note:** The Activity 3–7 labels below are historical log labels. For the single current roadmap starting at Activity 1, use [personalized-learning-canonical-roadmap.md](personalized-learning-canonical-roadmap.md). Its numbering supersedes the labels in this historical report; completed work is not to be repeated.

## Activity 3 — Backend models and initial migration

**Status:** Implemented in this project copy; this is a persistence foundation, not a usable learner feature yet.

### What changed

- Added the dedicated Django app `backend/learning` and registered `LearningConfig` in `backend/config/settings.py`.
- Added an initial additive migration at `backend/learning/migrations/0001_initial.py`, dependent on the current school-domain migration and the configured Django user model.
- Added learning-owned models for profiles and school/public scope, student invitations and guardian approval state, configurable learning frameworks/topics, resources and translations, learning paths/items, preferences, goals/saved items, idempotent activity events, learner-owned project/work records, recommendation metadata, AI usage metadata, and learning audit events.
- Added database constraints/indexes for account-scope shape, unique student linkage, resource/path/project/audit tenant scope, age/grade ranges, unique path positions, one-target saved/recommendation records, invitation state, and idempotent activity keys.
- Added model validation against cross-school resource/path references and guardian/student consistency.
- Added 16 focused model tests. The learning app does not reference marks, exams, report cards, fee operations, interventions, or any student academic weakness data.

### Verification run

Executed from `backend/` with `DJANGO_DEBUG=True`:

- `python3 manage.py check` — passed, no system-check issues.
- `python3 manage.py makemigrations --check --dry-run` — passed, no model/migration drift.
- `python3 -m py_compile learning/models.py learning/tests.py learning/apps.py` — passed.
- `python3 manage.py test learning --verbosity=1` — 16 tests passed.
- `python3 manage.py test --verbosity=1` — full existing project suite passed: 1,112 tests. Django printed pre-existing test-environment warnings/log messages about missing `staticfiles/`, a short JWT key, an EOF marker, and an unreachable SMS provider; they did not fail the suite.

The test runner applied the full migration graph, including `learning.0001_initial`, to its temporary test database. No application database was intentionally migrated in this activity.

### What is not implemented

There are no learning APIs/serializers, login/signup/invitation claim flow, permission classes, account creation, email verification, guardian UI/process, resource publishing workflow, learner or teacher screens, recommendation engine, AI provider/gateway, external content fetch, or offline learning. AI usage fields are metadata only and store no raw prompt or response. Models do not make an invitation or account usable by themselves.

### Applying the schema later

After reviewing and backing up the target deployment database, run the usual project migration command from `backend/` in the target environment:

```bash
python manage.py migrate
```

Do not enable registration, AI, or learner access based on the presence of these tables. Those capabilities remain disabled until their own implementation and security activities are complete.

### Product decisions still gating later account and AI work

Public adult verification/email delivery; guardian identity and consent verification for minors; school-admin invitation authority; permitted teacher/admin visibility into learner activity; catalogue licensing/review rules; provider contracts, data retention and budget; and production private file storage are not resolved by this schema activity. Existing academic, reports and financial workflows were not changed.


## Activity 4 — School learner identity, invitations and permissions

**Status:** Implemented in this project copy. This is the account-linking foundation; it is not a public self-registration or full learning product release.

### What changed

- Added learning-specific permission classes and API routes under `/api/learning/v1/` for full school-admin invitation listing/creation/revocation, linked-guardian approval, and student invitation claims.
- Only an authenticated, active, non-deputy school administrator who is neither a Django staff user nor superuser can manage invitations. School admins see/manage only their own school; cross-school student/invitation lookups return 404. Superadmin, deputy, teacher and guardian roles do not gain school-admin invitation privileges.
- Invitation claim codes contain high-entropy random material; only SHA-256 hashes are stored. The raw code is returned once at creation to the full school administrator and never appears in list responses. Default expiration is seven days (configurable, capped at thirty days); claim/admin/guardian operations have dedicated rate limits.
- A student must be active, not already linked to a learning profile, and belong to the administrator’s school. Students under 18 or with unknown/implausible birth dates require an active, already-linked guardian; if no linked guardian exists, an invitation cannot be issued. The guardian must authenticate with their existing Marian account and approve the exact linked student’s invitation. A claim rechecks the relationship, invitation state/expiry, school/student match, school suspension and active student status.
- Claiming creates a normal, non-staff, non-superuser Marian user, links it to the invited `Student` using `LearningProfile`, validates the password with Marian’s configured Django validators, records minimal learning audit events, and consumes the invitation transactionally. Student identity is exposed by the existing `/api/auth/me/` as `student`; existing superadmin, school admin, teacher, staff and parent precedence is preserved. A manually provisioned public learner profile resolves as `public_learner` without a school.
- School-linked learning profiles are now included in Marian’s existing school-suspension permission check. Public adult self-registration remains unavailable because email verification is not configured; no guardian account creation or outbound invitation delivery was added.

### Verification run

Executed from `backend/` with `DJANGO_DEBUG=True`:

- Python syntax compilation for learning account modules and modified auth/suspension modules — passed.
- `python3 manage.py check` — passed, no system-check issues.
- `python3 manage.py makemigrations --check --dry-run` — passed, no schema changes required for Activity 4.
- `python3 manage.py test learning --verbosity=1` — 31 tests passed (16 model/schema tests and 15 account/permission tests).
- `python3 manage.py test --verbosity=1` — full project suite passed: 1,127 tests.

The tests emitted non-failing environment/test logs (missing collected `staticfiles/`, short development JWT key warning, schema-generation serializer notices, and existing simulated SMS/backup logs). They did not fail the suite.

### Manual steps and limitations

- The administrator must securely deliver the one-time claim code to the student’s linked guardian outside Marian; no email/SMS delivery is configured. The code is visible only in the creation response and cannot be recovered from the database.
- Students can authenticate with the existing Marian username/password login, and `/api/auth/me/` returns their student identity, but the student-facing dashboard/UI and account recovery for learners are not implemented in this activity.
- Independent public account registration is deliberately disabled until a real verified-email path and public-minor/guardian policy are approved and built.
- This activity adds no new migration and does not alter existing school, student, academic, report, billing or fee records. The prior learning schema migration is applied only to temporary test databases during tests, not to the application database.
- Learning catalogue, progress, content APIs, teacher/admin learning screens, AI provider integration, offline support and all other product capabilities remain future activities.


## Activity 5 — Learner self-service profile and preferences

**Status:** Implemented in this project copy. The scope is deliberately limited to a learner’s own profile and preferences; it does not introduce catalogue, content, goals, saved-item, progress, or AI APIs.

### What changed

Added `GET` and `PATCH /api/learning/v1/me/`. The caller is resolved from the authenticated user’s `LearningProfile`; the request cannot provide a profile, school, student, user, age-band, account-kind, or consent identifier. The response exposes only account kind, locale, age/consent state for that same account, and the caller’s preference values—it does not expose an exact birth date or school/student IDs.

Learners can choose an interface locale from English/Kiswahili (`en`, `sw`, `en-KE`, `sw-KE`) and update their own topic IDs, preferred language codes, learning formats, difficulty, and recommendation on/off setting. Topic IDs must reference active topics; string lists are normalized, distinct and bounded; unsupported fields or choices are rejected. Updates are partial and transactional. A read with no existing preference row returns defaults without creating a database record. The endpoint has an authenticated-user rate limit.

Only an active school student whose school/student links still match and whose consent state passes the age-based gate, or an eligible adult public learner profile, may use this endpoint. School suspension is enforced. School-member/staff profiles are intentionally outside this learner endpoint and require their own later policy and UX.

### Verification run

Executed from `backend/` with `DJANGO_DEBUG=True`:

- Python syntax compilation of the new self-service modules — passed.
- `python3 manage.py check` — passed, no system-check issues.
- `python3 manage.py makemigrations --check --dry-run` — passed, no schema changes required.
- `python3 manage.py test learning --verbosity=1` — 48 learning-domain tests passed (models, identity lifecycle and self-service API).
- `python3 manage.py test --verbosity=1` — full project suite passed: 1,144 tests.

### What remains out of scope

There is no learner frontend yet, and this API does not browse or return learning content. Goal CRUD, saved items, progress events, resource/path catalogue APIs, teacher/staff self-service, and AI remain later activities. Public registration stays disabled pending real email verification; the self-service API accepts only already provisioned public adult profiles. This activity changes no models or migrations and does not touch application database records or existing academic/financial workflows.


## Activity 6 — Learner-owned learning goals API

**Status:** Implemented in this project copy. This activity adds only self-service goal management; it does not create a catalogue, learner content screens, saved-item or progress APIs, or AI features.

### What changed

Added `GET/POST /api/learning/v1/goals/` and `GET/PATCH/DELETE /api/learning/v1/goals/<goal_id>/`. Requests use the same active learner permission, age/guardian-consent gate, school-suspension check, and authenticated-user rate limit as the learner profile endpoint. Goal queries are always filtered by the caller’s own `LearningProfile`; another learner’s goal is concealed as 404. Client-supplied profile, student, school, user, or state-on-create fields are rejected.

Learners can create goals with a required title and optional description, topic, published learning path, and target date; list/filter their own goals; partially update fields and lifecycle state; and clear optional links/dates. Topic links must be active. Path links must be published and either public or in the learner’s own school. Path metadata is rechecked before serialization so stale or directly inserted cross-school links are never exposed. Input bounds and date/state values are validated, and writes use transactions/row locks for ownership and selected links.

Deleting is a soft close: the goal row is retained, state becomes `closed`, and `closed_at` is set. Completed and closed goals receive a terminal timestamp; reopening to an active/paused state clears it. Collection responses are bounded to 200 rows and disclose whether more rows exist.

### Verification run

Executed from `backend/` with `DJANGO_DEBUG=True`:

- Python syntax compilation — passed.
- `python3 manage.py check` — passed, no system-check issues.
- `python3 manage.py makemigrations --check --dry-run` — passed; no schema change required.
- `python3 manage.py test learning --verbosity=1` — 63 learning-domain tests passed.
- `python3 manage.py test --verbosity=1` — full project suite passed: 1,159 tests.

### What remains out of scope

There is no frontend for goals, no browse API to select topics or paths, and no learner content access in this activity. The path/topic IDs must currently come from separately provisioned content data; a future catalog API must provide discovery and enforce age suitability before any content is opened. Goal CRUD does not read examination, report, billing, or financial data. No model migration was needed, and this activity does not modify existing academic or financial workflows.


## Activity 7 — Read-only learner catalogue API

**Status:** Implemented in this project copy. This activity provides learner-safe catalogue discovery and read access; it does not add publishing or authoring workflows, frontend screens, progress, saves, or AI.

### What changed

Added authenticated, read-only endpoints under `/api/learning/v1/catalog/`:

- `GET /topics/` lists active topics, with framework, parent, topic-type, locale-label and age filtering.
- `GET /resources/` and `GET /resources/<id>/` list and read eligible learning resources. Supported filters are `lang`, `topic_id`, `framework`, `difficulty`, `resource_type`, and bounded `q` search. `resource_type` is used instead of DRF’s reserved `format` query parameter.
- `GET /paths/` and `GET /paths/<id>/` list and read eligible learning paths with ordered steps and safe resource references.

All routes require an active eligible learner profile and preserve school-suspension enforcement. Visibility is inferred from that profile: public learners see only shared/public records; school learners see shared records plus their own school’s records. Out-of-scope detail requests return 404. The catalogue has a separate authenticated-user throttle (120 requests/minute by default; test override remains isolated).

Content fails closed unless its status is published and reviewer, review timestamp, and publication timestamp are present. Retired resources, unreviewed/draft translations, inactive taxonomies, wrong-language content, and externally sourced resources without documented rights or HTTPS links are hidden. A path is not returned if one of its linked resources is missing, unpublished, age-inappropriate, unlicensed, wrong-language, or outside the learner’s scope; this prevents stale database references from exposing another tenant’s content.

Age filtering uses the linked student’s date of birth server-side and never returns it. A mismatched age-band/DOB or missing student DOB receives only content with no age bounds. Public accounts are adult-only and, without exact DOB, are evaluated at the conservative age floor of 18. No server-side external URL fetching occurs. Stored body/instructions are returned as text with markup stripped. Private storage keys are never serialized, and file-only resources are hidden until authorized file delivery exists.

### Verification run

Executed from `backend/` with `DJANGO_DEBUG=True`:

- Python syntax compilation — passed.
- `python3 manage.py check` — passed, no system-check issues.
- `python3 manage.py makemigrations --check --dry-run` — passed; no schema changes required.
- `python3 manage.py test learning --verbosity=1` — 77 learning-domain tests passed, including 14 catalogue-specific tests.
- `python3 manage.py test --verbosity=1` — full Marian suite passed: 1,173 tests.

The full test run printed existing non-failing environment warnings/logs (missing collected `staticfiles/`, short development JWT key, and simulated SMS/backup messages). They did not fail the suite. Tests use temporary databases; this activity introduces no migration and changes no official academic or financial workflow.

### What remains out of scope

There is no catalogue publishing/review UI or public-account email verification flow, and no learner frontend has been added. No private asset download/streaming endpoint exists; resources dependent on an uploaded file alone remain unavailable. Saved items, progress events, recommendations, teacher/admin learning operations, and AI remain later activities. Content can be discovered only when a trusted process has populated review/publication metadata; this API does not claim to provide a publishing workflow.


## Canonical Activity 7 — Learner saved-items API

**Status:** Implemented in this independent project copy, following the canonical roadmap in `personalized-learning-canonical-roadmap.md`. The older Activity 7 catalogue entry above is retained as a historical numbering log; it is not a request to repeat catalogue work.

### What changed

- Added `GET`, `POST`, and `DELETE /api/learning/v1/saved/`. POST and collection DELETE accept exactly one `resource_id` or `path_id`. A successful first save returns 201; an already-saved item returns 200 with the existing saved-record ID. Collection DELETE always returns 204 for an absent, stale, or existing own save, so repeated removals are safe.
- Added `DELETE /api/learning/v1/saved/<saved_item_id>/`. It deletes only a row owned by the caller's learning profile; foreign or nonexistent rows return the same 404 response.
- The caller's identity is derived from Marian authentication and `ActiveLearnerSelfService`; client-provided profile, school, student, or user IDs are not accepted. School learners may save public and same-school content; public adult learners may save only public content.
- Save requests and list serialization reuse the catalogue's current language, publication/review, licensing, scope, age, and path-item visibility checks. Stale, retired, newly hidden, cross-tenant, wrong-language, or age-ineligible items are omitted; stale records remain removable. Saved responses never expose private storage keys.
- Lists fetch at most 201 saved rows and return at most 200 serialized entries with a `truncated` flag. Existing database uniqueness constraints provide one save per profile/item; no new model or migration was needed.
- Added regression coverage for resources and paths, repeat save/remove, eligibility and malformed IDs, public-versus-school boundaries, foreign-owner 404/no-op behavior, stale hidden rows, age/language changes, and the 200-item cap. Updated the canonical roadmap and API architecture notes.

### Verification run

Executed from `backend/` with `DJANGO_DEBUG=True`:

- `python3 manage.py check` — passed, no system-check issues.
- `python3 manage.py makemigrations --check --dry-run` — passed; no changes detected.
- `python3 -m py_compile learning/saved_items_api.py learning/test_saved_items_api.py learning/urls.py` — passed.
- `python3 manage.py test learning --verbosity=1` — 89 learning-domain tests passed.
- `python3 manage.py test --verbosity=1` — full Marian suite passed: 1,185 tests.
- OpenAPI generation reported no saved-items diagnostics. The repository still has broader pre-existing schema issues (1004 errors / 14 warnings across the existing API), outside this activity.

Existing non-failing test-environment messages included a missing collected `staticfiles/` directory, short development JWT-key warnings, and simulated backup/SMS logs. Tests used temporary databases; the production database was not migrated or modified.


## Canonical Activities 8 and 9 — Path participation and content governance

**Status:** Activity 8 is **PARTIAL / SAFE CORE IMPLEMENTED**. Activity 9 is **PARTIAL / PUBLICATION POLICY-GATED**. This work was authorized as a two-activity override; the uploaded source ZIP and primary Marian repository remain untouched.

### Activity 8 — Path participation and validated progress events

Added `POST /api/learning/v1/paths/<path_id>/start/` and `GET /api/learning/v1/participation/paths/`. Start is idempotent for the caller, currently visible published path, and exact path version. Participation is tied to the authenticated learner’s own eligible `LearningProfile`; tenant, publication, age, language, resource, and suspension checks reuse the catalogue’s visibility rules. Starts lock and revalidate the path, its items, and contributing resources inside the transaction. Listing returns only the caller’s participation for paths still visible to that learner.

Added owner-only `GET/POST /api/learning/v1/activity-events/`. POST requires a UUID idempotency key, exactly one currently visible resource or path-item target, and one of the strict `started`, `progress`, or `feedback` schemas. Request bodies are limited to 8 KiB. Progress accepts only an allowlisted self-assessment checkpoint; feedback accepts only a 1–5 integer rating. Client timestamps, duration, arbitrary fields, completion, submission, and completion totals are rejected. Server timestamps are assigned, duration remains null, and no clicks/time are rewarded. Replays with the same key and same payload return the existing event; conflicting key reuse returns 409. Path-item activity additionally locks and revalidates the current path, items, resources, and participation in the event transaction. No teacher/admin learner-history route exists.

Completion is deliberately not inferred from starts, views, clicks, time, or client claims. New path items accept only `completion_rule="view"`, which never completes a step. Participation stays `in_progress` and has no client transition to completed until the platform implements verifiable learning-outcome evidence (for example, a reviewed work/assessment workflow). This preserves truthfulness but leaves automated path completion for a future activity.

### Activity 9 — Learning content governance and publication gate

Added school-scoped resource/path draft collection and detail APIs under `/api/learning/v1/studio/`, submission, request-changes/approval review, review queue, archive/retire, immutable version snapshots, and minimal audit events. Real Marian `TeacherProfile` and non-deputy `SchoolAdminProfile` records establish role and school. Teachers manage their own drafts; full school administrators review within their school; an author cannot review their own content. Translation edits, submissions, and reviews lock the parent then translation row and recheck state in one transaction, preventing an edit from inheriting an approval based on stale text. Deputies, Django staff/superusers, conflicting teacher/admin profiles, and cross-school records do not gain interchangeable privileges. No shared-catalogue authoring route exists.

Submission validates source/provenance, licence or documented rights, attribution, normalized language, age range, and content-specific metadata. External-origin resources are HTTPS link-only and cannot contain copied third-party text; no server-side fetch, scraping, or redistribution path was added. Human translations for both resources and path metadata have draft/submission/review/approval states, independent school-admin review, history snapshots, and tenant-scoped queue entries. The learner catalogue does not yet localize translated path-step instructions; those records are not exposed to learners.

A school administrator can approve content for a later publication decision, but every `publish` API call is deliberately blocked with HTTP 503 (`content_publication_policy_unapproved`) and leaves the record unpublished. This gate cannot be bypassed with an environment flag. It remains until product-owner approval of licensing/rights allowlists, moderation/review standards, and shared-catalogue ownership. Approved content is not automatically exposed to learners. Existing live school resources may be retired by their full school administrator; shared catalogue content is not mutable through this API.

### Verification run

Executed from `backend/` with `DJANGO_DEBUG=True`, and with production database variables unset. Django tests created a disposable SQLite test database and applied the additive learning migrations there only.

- `python manage.py check` — passed, no system-check issues.
- `python manage.py makemigrations --check --dry-run` — passed, no model/migration drift.
- `python -m py_compile` for changed Activity 8–9 Python modules, tests, and migrations — passed.
- `python manage.py test learning.test_activity_api learning.test_content_api --verbosity 1` — **22 tests discovered: 20 passed and 2 database-specific concurrency tests skipped**, because SQLite does not implement `SELECT FOR UPDATE`.
- `python manage.py test --verbosity 1` — **1,207 tests discovered: 1,205 passed and the same 2 concurrency tests skipped**.

Existing non-failing environment warnings/logs included missing collected `staticfiles/`, the short development JWT key, schema-generation/operation-ID collision notices, and simulated backup/SMS logs. The new row-lock races require a PostgreSQL-like test backend to execute rather than skip; test them on that backend before production rollout. No production database was migrated.

### Remaining limitations

No learner or teacher/admin UI is included. Automated path completion remains disabled until verifiable step evidence is implemented. Publication remains fail-closed pending the named policy approvals. Resource and path metadata translations can be reviewed, but translated path steps are not yet rendered by the learner catalogue. At the time of that Activity 8–9 verification pass, Activity 10 and later activities remained out of scope.


## Canonical Activity 10 — Secure private-file lifecycle

**Status:** Implemented in this independent source copy; **production use is deployment- and policy-gated**. Activity 9 publishing remains independently blocked. Activity 8 remains **PARTIAL** until server-verifiable outcome rules exist.

### What changed

- Added `LearningPrivateAsset` metadata and additive migration `learning.0004_private_asset_lifecycle`. Database rows keep only an opaque storage name, normalized content type, byte length, SHA-256 digest, scan state, uploader, and lifecycle timestamps—not file bytes or original filenames.
- Added school-authorized Studio upload/list/delete and reviewer-download APIs, plus an authenticated learner download stream. Every delivery rechecks current user, school/resource visibility, publication/review state, language, age suitability, consent, and suspension. Private storage names are not serialized and there are no public or bearer download URLs.
- Uploads are validated from file bytes and accept only PDF, JPEG, and PNG. Limits are 10 MiB per file, 10 active attachments and 50 MiB per resource; PDFs are capped at 100 pages and rebuilt without actions or attachments; images are decoded and re-encoded with 10,000-pixel dimension and 40-megapixel limits. Malformed, encrypted, animated, SVG, archive, and unsupported inputs are rejected.
- Each object is recorded as quarantined before scanning. Only scanner exit code 0 marks a file clean; an infected result, missing scanner, timeout, exception, or unknown scanner result leaves it unavailable. A clean scan is required for file delivery and for content submission/review. Clean file-backed resources may appear in the learner catalogue only after the ordinary Activity 9 publication and eligibility gates pass.
- Development filesystem storage is outside `MEDIA_ROOT`, rejects overlap/symlink roots, and uses restrictive directory/file permissions. Production has no local fallback and returns unavailable until an operator-selected backend implements `save/open/delete` and explicitly declares `is_private=True` and `is_durable=True`. These declarations are a backend contract, not proof of the provider’s configuration; the selected service still requires owner approval and operational verification.
- Deletion first revokes application access, retains a minimal tombstone, then removes bytes; failed physical cleanup can be retried. A full school administrator must archive non-draft content before deleting its attachment, preserving the currently reviewed/published version while live. No automatic retention period or purge schedule is invented.
- Added focused coverage for tenant/role boundaries, normalization, malformed and oversized files, scanner outcomes, quarantine, safe headers, catalogue/download eligibility, storage failure/retry, state races, production fail-closed behavior, storage-contract declarations, and cleanup after archiving.

### Verification run

Executed from `backend/` with `DJANGO_DEBUG=True`. Production database environment variables were unset; Django tests created and destroyed disposable SQLite test databases only.

- `python manage.py check` — passed, no system-check issues.
- `python manage.py makemigrations --check --dry-run` — passed, no model/migration drift.
- `python -m py_compile` for changed Activity 8–10 Python modules, tests, and migration — passed.
- `python manage.py test learning.test_assets_api learning.test_activity_api learning.test_content_api --verbosity=1` — **39 tests discovered: 37 passed, 2 skipped**. The skips are database-specific row-lock/concurrency cases because SQLite does not implement `SELECT FOR UPDATE`.
- `python manage.py test --verbosity=1` — **1,224 tests discovered: 1,222 passed, 2 skipped** (the same concurrency cases).

The full run emitted existing non-failing test-environment notices, including the missing collected `staticfiles/` directory, short development JWT-key warning, API-schema serializer/operation-ID diagnostics, and simulated backup/SMS logs. They did not fail the suite. PostgreSQL-like execution of the two concurrency tests remains required before production rollout. No production database was migrated or changed.

### Remaining owner decisions and release gates

- Select and approve a durable private-storage provider/backend and verify that its actual bucket/container policies prevent public access and that its durability/backup behavior meets requirements.
- Select and configure the malware scanning service/executable, with operational monitoring and failure handling; until available, files remain quarantined and production upload is unavailable.
- Approve retention, audit, deletion/retry, and any scheduled purge policy; no automatic expiry has been assumed or enabled.
- Separately approve Activity 9 licensing/rights allowlists, moderation/review standards, and shared-catalogue ownership before enabling publication. The `publish` endpoint remains hard-gated and is not made available by Activity 10.
- Activity 8 path completion remains partial until server-verifiable learner-outcome rules exist; the two PostgreSQL-specific concurrency cases should be run against the intended database before rollout.


## Canonical Activity 11 — Account and guardian operations

**Status: PARTIAL / DEPENDENCY-GATED; safe core implemented.** See [`activity11-account-operations.md`](activity11-account-operations.md) for the API matrix, configuration, and explicit release gates. The approved age policy is confirmed and enforced: under 10 is school-managed only; ages 10–17 require verified guardian involvement and consent for independent access; 18+ may self-register only when age/contact verification is actually integrated; unknown age is barred from protected learning features. The independent minimum defaults to 10 and cannot be configured lower.

### What changed

- Added shared age-policy logic and a provider-neutral account-provider contract/status endpoint. A provider module path alone never makes capabilities ready. Public registration remains HTTP 503 and does not create accounts or simulate verification.
- Added additive migration `learning.0005_learninginvitation_delivery_status_and_more`, including conservative conversion of legacy age bands and safe handling of ambiguous DOB records.
- Preserved Marian authentication and school workflows. Roster-derived age and consent gates are enforced for school-managed learners; unknown-age accounts may use existing Marian authentication but not protected learning endpoints.
- Added non-destructive lifecycle requests/cancellation, linked guardian summaries and consent withdrawal, minimal assigned-teacher progress, school aggregates and bounded school account listings, full-admin account suspend/reactivate, invitation delivery status, and audited sensitive reads/state changes.
- Expired unclaimed invitation records are transactionally retired before reissue; the expired raw token cannot be reused. Active invitation delivery remains disabled: no email/SMS is sent and no token is changed.
- Added responsive public status and school-code claim, learner account/lifecycle, guardian-linked learner/pending invitation approval, and school-admin summary/list/state/invitation-candidate/create/revoke/status screens. Provider-dependent recovery and independent registration are clearly unavailable. Existing Marian login/password recovery remains unchanged.
- Audited school invitation and candidate list reads, as well as pending guardian-invitation reads; results are tenant/relationship scoped and bounded. Added policy, provider, account API, role/tenant, guardian withdrawal/approval, deletion safety, invitation reissue/resend, and frontend policy tests.

### Final verification

All Django checks and tests were run with production database environment variables unset. Django used only disposable SQLite test databases; no production or source-copy application database was migrated.

- `python3 -m compileall -q api config learning schools` — passed.
- `python3 manage.py check` — passed; no system-check issues.
- `python3 manage.py makemigrations --check --dry-run` — passed; no migration drift.
- Focused Activity 11 account, guardian, invitation, age-policy, provider, self-service, and role-sweep run — **81 tests passed**.
- Full Marian backend suite — **1,251 tests discovered; 1,249 passed and 2 skipped**. The two skips are row-lock/concurrency tests because SQLite does not implement `SELECT FOR UPDATE`; run them against the intended PostgreSQL-like database before production rollout.
- Frontend `npm test` — **10 passed, 0 failed**.
- Frontend `npm run build` — passed; Vite built the production bundle.
- Frontend `npm run lint` — completed with **0 errors and 78 warnings**. This is the same warning count recorded before the final Activity 11 UI changes; warnings are in the existing Marian frontend and do not fail the command.

The full backend run printed existing non-failing test-environment notices (missing collected `staticfiles/`, short development JWT key, backup/restore test logs, an EOF marker, and simulated unreachable SMS provider). They did not fail the suite. A new full-source archive, `Marian_Personalized_Learning_Activities_8_to_11.zip`, was CRC-tested and verified to include the required source/migration/docs while excluding databases, environment secrets, private job/media files, dependencies, build outputs, caches, and nested archives. The existing Activities 8–10 and 8–9 ZIPs were checksum-verified unchanged. The new archive's SHA-256 is provided in its adjacent checksum sidecar and final handoff.

### Unimplemented integrations and release gates

Real provider adapters and orchestration for email/SMS/contact and age verification, independent verified guardian identity/new-consent capture, public independent registration, automated invitation delivery, provider-backed recovery, guardian-/school-assisted recovery, retention/purge execution, and assigned-case moderator workflows remain incomplete and disabled. School invitation creation/revocation/status, linked-guardian school-invitation approval, and school-code claim screens reuse Marian accounts and work without simulating delivery. The retention-days setting is informational only. Lifecycle requests block learning access but do not hard-delete Marian users, official student records, or learning history. No production migration or deployment has occurred. PostgreSQL-like execution of the two row-lock concurrency tests remains a production-readiness gate.


## Independent-first learner profiles and separate individual subscriptions

**Status: access-control and subscription foundations implemented; independent registration and payment activation remain disabled.** The learner's Marian authentication is reused. Independent learning profiles are not automatically linked to a school or student; future school linking for recommendations remains deferred. School-managed invitation/guardian workflows and existing Marian billing are not replaced.

Personalized Learning is a separately paid individual add-on. The new subscription domain is separate from `StudentFee`/`FeePayment`; school fees/subscriptions do not grant Premium. Additive migration `learning.0006_individual_subscription_access_tiers` adds Free/Premium access tiers and individual plan/subscription/provider-transaction models. `learning.0007_seed_individual_learning_plans` seeds an active Free plan and an inactive Premium plan with no price, currency, recurring interval, or entitlements invented. Backend entitlement checks default to Free and require an eligible profile plus an in-period active subscription and a provider-verified succeeded transaction that matches the plan amount/currency.

Public plan/capability, authenticated learner status/history, and checkout-request routes are available under `/api/learning/v1/subscriptions/`. Checkout is hard fail-closed: no real payment adapter, verified webhook/event flow, or settlement integration exists, so the endpoint returns unavailable and creates no payment or subscription record. Independent signup also remains HTTP 503 until age/contact and guardian-identity/consent integrations are real and verified. A populated provider setting alone cannot enable capabilities. Premium remains inactive until pricing, billing interval/currency, and entitlements are approved. No AI tutoring endpoint exists; AI is not an advertised entitlement. Resource/path access tiers are enforced server-side across catalog access and dependent resource/goal flows. The new public subscription metadata routes have been added to the parent-role sweep's allowlist because they contain no learner-specific data.

### Verification for this scope

Executed against the isolated source copy with `DJANGO_DEBUG=True`; test runs used a disposable SQLite database. No production migration, payment, signup, or deployment was attempted.

- `python manage.py makemigrations --check --dry-run` — passed; no model/migration drift.
- Focused subscription and content-governance suites — **20 tests passed, 1 SQLite-only row-lock/concurrency test skipped**; included default Free access, expired/unpaid Premium denial, backend premium access denial across protected surfaces, guardian payer scoping, no checkout records/school fee writes, and content access-tier revision snapshots.
- Full Marian backend suite, after correcting the role-sweep allowlist for public non-learner-specific plan/capability endpoints — **1,257 tests discovered; 1,255 passed and 2 skipped**. Both skips require a database supporting `SELECT FOR UPDATE`; run them on the intended PostgreSQL-like backend before production rollout.
- Frontend `npm test` — **10 passed, 0 failed**.
- Frontend `npm run build` — passed; Vite production bundle built.
- Frontend `npm run lint` — **0 errors, 78 warnings**. The warnings are existing project-wide diagnostics and do not fail the command.

Existing non-failing test-environment notices include missing collected `staticfiles/`, short development JWT-key warnings, schema serializer/operation-ID diagnostics, and simulated SMS/backup logs. The signup, payment, age/contact verification, independent guardian verification/consent, Premium pricing, and school-linking blockers above remain real product/release gates; these passing tests do not certify those integrations or production readiness.


## Canonical Activity 12 — Learner learning experience

**Status: IMPLEMENTED / CATALOGUE-CONTENT-POLICY-GATED.** Work is confined to this isolated source copy. No new backend endpoint, model, migration, authentication flow, school association, deployment, or production data change was added. A follow-up read-only audit did harden the existing goals and catalogue list logic without changing their contracts.

### What changed

- Added `frontend/src/LearningExperience.jsx` and `LearningExperience.css`, a distinct responsive/mobile-first learner shell with learner-only navigation. `Dash.jsx` routes only existing Marian `student` and `public_learner` identities into this shell and skips the school dashboard API for them. Existing login/logout, account screens, and non-learner `Shell` hash tabs remain intact. School/public content separation and protected-feature eligibility are checked by the existing APIs; the frontend does not infer a school link or request school-only features for public learners.
- Added approved-content discovery/search and topic, difficulty, and resource-format filters; resource detail, source/rights attribution, safe HTTPS external links, and protected private-file downloads; visible path list/detail and idempotent start/continue; and a disclosure that path-step instructions are not localized by the learner catalogue yet.
- Added learner-owned goal create/edit/pause/resume/self-mark-complete/reopen and soft-close, saved-item list/add/remove, own-account continue/recent history, and explicit `started`/allowlisted self-reported `progress` check-ins. Path-step check-ins remain unavailable until the caller has an in-progress participation. The UI does not submit client completion, duration, time-spent, or arbitrary activity data; it does not imply verified mastery/path completion, time rewards, AI tutoring, or premium checkout.
- Added a content-language selector that persists `preferred_languages` through the existing learner `/me/` PATCH contract. Server language/catalogue filtering remains authoritative. Shared loading/error/empty states cover inaccessible or policy-gated content; the existing account settings component is mounted under the new shell.
- Added `learningExperienceUtils.js` and focused Node tests for role routing, language normalization, safe/length-bounded query construction, secure UUID idempotency keys, allowlisted activity targets/checkpoints, and rejection of completion claims.
- Reused current catalogue eligibility checks when accepting or serializing goal-linked topic/path names, covering age, language, review/publication, scope/tier, and linked path-item visibility. Resource/path list caps now scan beyond hidden candidates until the 201st visible row or exhaustion, and `truncated` reflects visible results. Added regression tests for stale/age-hidden goal links and hidden candidates ahead of visible catalogue rows.
- Clarified that learning activity is not public while limited summaries may be visible to assigned teachers for school-managed learners. Darkened the footer note to `#586a6e`, measured at 5.40:1 against `#f7faf9` (above the 4.5:1 WCAG AA normal-text threshold).

### Verification for this scope

Executed against the isolated source copy. Backend commands used `DJANGO_DEBUG=True`, a one-off non-production test secret, and blank production database variables; Django created and destroyed a disposable SQLite test database.

- Focused catalogue and goal regression run: `learning.test_catalog_api` and `learning.test_goals_api` — **33 tests passed**.
- `python manage.py check` — passed; no system-check issues.
- `python manage.py makemigrations --check --dry-run` — passed; no migration drift.
- Python syntax compilation for the changed catalogue and goals modules/tests — passed.
- Full Marian backend suite — **1,261 tests discovered; 1,259 passed and 2 SQLite row-lock/concurrency tests skipped**. Run the skipped lock tests against the intended PostgreSQL-like database before production rollout.
- Frontend `npm test` — **15 passed, 0 failed**.
- Frontend `npm run build` — passed; Vite production bundle built.
- Frontend `npm run lint` — **0 errors, 78 warnings**, unchanged from the pre-Activity-12 count. The remaining warnings are existing Marian frontend diagnostics.

The full run printed existing non-failing environment/test notices (missing collected `staticfiles/`, short development JWT-key warning, schema serializer/operation-ID diagnostics, and simulated backup/SMS logs). No browser-driven device/accessibility session was run. These checks do not replace PostgreSQL-like concurrency tests or live learner/account verification.

The same authorized full-source ZIP was refreshed with **687 entries**, CRC-tested, and checked for the required Activity 12 code/tests/docs and exclusion of databases, private/runtime data, environment secrets, dependencies, build outputs, caches, and nested archives. Its adjacent `.sha256` sidecar was verified. The Activity 7, Activities 8–9, Activities 8–10, and Activities 8–11 ZIP archives were checksum-verified unchanged.

### Remaining limits and dependencies

Activity 9 publishing remains hard-disabled pending product-owner approval of licensing/rights allowlists, moderation/review standards, and shared-catalogue ownership; consequently learner screens may correctly show empty catalogue states. Existing eligible published items are still subject to server-side age, consent, scope, rights, language, publication, tier, and suspension checks. Activity 8 path completion remains unverified and `in_progress`; client check-ins are self-reports, not proof of learning. Path-step translations are not rendered by the learner catalogue. Activity 11 independent registration, age/contact verification, guardian identity/consent capture, provider-backed recovery/delivery, and real payment activation remain disabled; this learner UI adds none of them. Full English/Kiswahili interface translation and broader mobile accessibility validation remain Activity 18 work.


## Canonical Activities 13–14 — Teacher Studio and Learning Administration Centre

**Status: IMPLEMENTED / CATALOGUE-PUBLISHING-POLICY-GATED.** Implemented in the independent project copy described by [activity13-14-teacher-studio-learning-centre.md](activity13-14-teacher-studio-learning-centre.md). The uploaded source ZIP and primary Marian repository remain untouched.

### Activity 13 — Teacher Studio

- Added a lazy-loaded teacher dashboard workspace with free, visible catalogue discovery for resources and learning programmes, topic browsing, search, and text detail. It does not bypass school scope, age/licence/review/publication checks, or paid access tiers.
- Teachers can create, edit, and submit their own private school resource/path drafts with existing provenance, licence/rights, attribution, age and review validation. Drafts remain private unless the existing content reviewer authorizes their next state. The publication API remains hard-gated.
- Added teacher-selected recommendations of currently eligible Free resources or paths only for a learner actively enrolled in a stream assigned to that teacher. The student and catalogue item are rechecked server-side, submissions are audited, and the learner's existing shell includes a recommendations inbox with keep/dismiss actions.
- Added assigned-learner learning participation summaries, bounded to currently assigned active students. The new list omits DOB, age band and account status and returns no exam/mark, report-card, attendance, fee, risk, prompt, or learner-work data. The legacy individual learning-summary route honors the new school Teacher Studio switch.
- This is not Activity 15's automatic deterministic recommendation engine and does not use academic weakness or performance signals.

### Activity 14 — Learning Administration Centre

- Added a lazy-loaded Learning Centre visible only to an active full school administrator. It includes school-only aggregate usage, school resource/programme/translation review, approved programme state, and tenant-scoped learner access, age, Teacher Studio and recommendation controls.
- Added migrations `learning.0008_learningschoolsettings` and `learning.0009_learningschoolsettings_learn_school_age_min_plausible`. Settings are per-school and audited. The database and API enforce 0–120 age bounds and min ≤ max; learner DOB is checked server-side and not returned. Deputies, superusers, Django staff, teachers, and conflicting teacher/admin identities cannot update the controls.
- Review-queue reads are audited using only aggregate counts. Translation approval does not publish its parent item. Admin aggregate screens do not expose independent public learners or teacher-level learner histories.
- Publishing remains HTTP 503 / policy-gated. No content has been seeded or published by this work.

### Verification for this scope

Executed in the isolated copy with `DJANGO_DEBUG=True` and a disposable SQLite test database; no application/production database was migrated.

- `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and `python -m compileall -q learning schools api` — passed.
- Focused staff/content-governance run — **24 tests passed, 1 SQLite row-lock/concurrency test skipped**.
- Full Marian backend suite — **1,270 tests discovered; 1,268 passed and 2 skipped**. Both skips require a database with `SELECT FOR UPDATE`; run them against the intended PostgreSQL-like database before deployment.
- Frontend tests — **15 passed, 0 failed**; Vite production build passed and the added screens are lazily loaded; lint — **0 errors and 78 existing warnings**, unchanged from the project baseline and no warnings in the new components.

No production deployment, migration, content publication, backend-provider enablement, or PostgreSQL concurrency verification was performed at the Activities 13–14 checkpoint. Activity 15 has since been implemented; see `activity15-deterministic-recommendations.md` and the canonical roadmap for current status.

The independent Activity 13–14 full-source ZIP was created with **625 files**, CRC-tested, and checksum-verified. It excludes local SQLite databases, `node_modules`, frontend build output, Python caches, the redundant local source-backup directory, nested ZIPs, and non-example environment secrets; `.env.example` templates remain included. Its SHA-256 is recorded in the adjacent `.sha256` sidecar. The uploaded Activity 12 source ZIP was preserved unchanged.


## Canonical Activities 18–19 — Motivation, localization, accessibility, analytics, and offline learning

**Status:** Implemented in this independent source copy; production and policy gates remain explicit.

### Activity 18

- Added `GET/PATCH /api/learning/v1/motivation/` for learner-owned motivation preferences and derived personal milestones, optional challenges, streaks, and counts. The calculations use only explicit learning activity and learner-owned goal state; there are no public rankings, click/time rewards, marks, reports, risk labels, or weakness signals.
- Added English and Kiswahili labels for the new motivation/offline controls and an interface-language-aware learner home panel.
- Added learner-controlled high-contrast and reduced-motion preferences, visible keyboard focus styling, responsive mobile panels, labelled fieldsets, live status/error messages, and touch-friendly controls.
- Added `GET /api/learning/v1/admin/learning-analytics/` for full school administrators only. It returns a 30-day, school-scoped aggregate of learning events and active learners, with no roster, independent-public learner records, academic data, or raw learner content. The response states the 30-day retention window; the actual retention/deletion job and product-owner approval remain operational gates.

### Activity 19

- Added additive models/migration `learning.0010_activity18_19` for revocable learner offline packages and idempotent operation receipts.
- Added learner-scoped `POST/GET /api/learning/v1/offline/packages/`, `POST /api/learning/v1/offline/sync/`, and package revocation. Packages are built only from currently visible content, bound to an opaque device ID, capped at 20 items/250 KB manifest, and expire after seven days.
- Added browser AES-GCM encryption with PBKDF2 key derivation and encrypted IndexedDB storage. The server does not receive the passphrase or store cleartext package bytes.
- Added idempotent operation IDs, safe replays, package membership checks, explicit conflict results, package expiry/revocation enforcement, and learner/tenant isolation.
- Added responsive learner preparation, unlock, sync, and forget controls. These controls clearly state that offline Personalized Learning does not include teacher marks, reports, fees, attendance, attachments, or automatic completion.

### Verification

- Django migration application, `manage.py check`, and `makemigrations --check --dry-run` passed.
- Focused activity 18–19 backend tests: 3 passed.
- Existing learning-domain suite: 174 tests passed; 2 existing SQLite row-lock tests skipped as before.
- Frontend tests: 15 passed.
- Vite production build: passed; one pre-existing large-chunk warning remains.

### Remaining gates

Human review of important Kiswahili translations, approved aggregate analytics retention/deletion operations, licensed offline content policy, device revocation operations, service-worker/content delivery verification for learner packages, PostgreSQL row-lock testing, and real mobile-device accessibility/offline testing remain Activity 20 release work. Existing teacher marks offline behavior is separate and unchanged.


## Canonical Activity 20 — Release readiness and full operational verification
**Status: TECHNICAL VERIFICATION COMPLETED / PRODUCTION GATES OPEN.**

Added `scripts/release_readiness.py`, `scripts/sqlite_backup_restore_rehearsal.py`, and [`activity20-release-readiness.md`](activity20-release-readiness.md). The release runner uses a disposable Django test database and a non-production secret; it never connects to or migrates a production database. The disposable backup rehearsal copies only temporary SQLite files.

### Verified in this source copy
- Django system checks, migration drift, Python compilation, Activity 18–19 tests, and the learning-domain suite pass.
- Frontend tests and production build pass.
- Existing role, school-isolation, cookie, suspension, migration, backup, provider-failure, and offline-marks tests remain in the source suite.
- Disposable backup/restore rehearsal passes.
- New Activity 18–19 learner controls have responsive, labelled, focus-visible, reduced-motion, contrast, and live-status UI behavior.

### Not falsely marked complete
The source-copy environment has no PostgreSQL server, so `SELECT FOR UPDATE` concurrency cases remain a PostgreSQL test gate. Production backup/restore/rollback requires an approved provider and isolated restore target. Storage/malware scanning, account/guardian/contact providers, payment activation, catalogue rights/publication, Kiswahili human review, analytics retention deletion, device revocation operations, service-worker delivery, and real Android/iOS screen-reader/offline testing require owner decisions, credentials, infrastructure, or real devices.

The package is staging-ready for those owner-controlled checks, not production-certified.


## Canonical Activity 15 — Explainable deterministic recommendations

**Status: IMPLEMENTED / CONTENT-AND-ENTITLEMENT-GATED.** Details are in [`activity15-deterministic-recommendations.md`](activity15-deterministic-recommendations.md), with the single activity sequence in [`personalized-learning-canonical-roadmap.md`](personalized-learning-canonical-roadmap.md).

Implemented `POST /api/learning/v1/recommendations/generate/` as a deterministic, server-side service. It uses only the authenticated learner’s own selected topic interests, active learner-set goals, preferred language/format/difficulty, and recent visible event target identities (`started`, `progress`, `feedback`). It does not use event details or duration, marks, exams, reports, attendance, fees, risk scores, prompts, or inferred weakness. Catalogue items are rechecked against publication/review, language, age, tenant, suspension, path-item, and current entitlement gates; suggestions are limited to eight active rows with a 30-day expiry. Persisted reason codes and dynamic English/Kiswahili explanation text expose only approved learning signals. Dismissals are honored; automatic personalization can be paused while teacher-selected suggestions remain visible. The preferences UI supports topic selection (up to ten), format/difficulty preferences, opt-out, and manual refresh. Generation, reading, and responses are audit-logged without recording selected interests or raw learning activity. No AI or payment integration was enabled.

### Activity 15 verification

- Focused recommendation API suite: **6 passed**.
- Django system check: **passed**; migration drift check: **no changes detected**.
- Full learning-domain suite: **183 tests, 181 passed, 2 skipped** (SQLite row-lock limitations).
- Final full Marian backend suite after Activity 15: **1,279 tests, 1,277 passed, 2 skipped** (the SQLite row-lock/concurrency tests require PostgreSQL-like verification).
- Frontend tests: **18 passed, 0 failed**, including Activity 15 preference-helper tests. Lint: **0 errors, 79 warnings**; no new Activity 15 file diagnostics were reported. Vite production build: **passed**, with the existing large-chunk warning.

The latest approved decision that eligible active Marian students receive learning access through their existing accounts without a redundant invitation is not yet fully implemented: Activity 11’s current account-linking path remains invitation/claim-based in some cases. Meaningful free access also depends on licensed content that may be published only after the Activity 9 rights/moderation/catalogue-ownership gate. Guardian-as-payer, configurable prices, provider-backed independent registration, and verified payment activation remain disabled/unimplemented. Do not describe these dependencies as live. No production database was migrated and no deployment occurred.


## Current update — 16 November 2026 (canonical Activity 17 quiz slice; Activity 20 runner hardening)

> The canonical activity sequence remains `personalized-learning-canonical-roadmap.md`; this is a current addendum, not a new Activity 21 and not a request to repeat historical work.

### Activity 17 — first usable practice quiz slice (PARTIAL)

Added the structured, bounded practice-quiz schema, resource field, private attempt record, and additive migration `learning.0012_learningresource_practice_quiz_learningquizattempt`. Teacher Studio now creates/edits original quiz drafts, preserves answer-key revisions, and shows keys only in its authorised school review workflow. The learner API returns key-free quiz questions, validates a strict attempt against the current visible resource version, scores answers on the server, applies idempotency and a dedicated throttle, stores no selected answers, and creates minimal server-authored completion evidence. Learners can answer and receive feedback in the mobile-responsive interface, with English/Kiswahili labels and explicit notice that practice is not a Marian examination mark or mastery certificate. No quiz is published; the existing policy-gated publication API is unchanged. Path completion, AI, code execution, simulations, project submissions, and outcome retention approval are not part of this slice. Details are in `activity17-practice-quizzes.md`.

### Activity 20 — runner isolation hardening

Hardened `scripts/release_readiness.py` to invoke subprocesses under a minimal environment allowlist, replace the development secret, remove inherited database/provider credentials, direct Django's SQLite **test-only** DB to a temporary directory, and avoid writing Python bytecode during syntax verification. Added unit tests proving database/provider secrets are not forwarded. The setting override applies only under `manage.py test` with the SQLite development backend; normal Marian database selection and PostgreSQL production configuration are unchanged. The disposable backup/restore rehearsal still touches only temporary SQLite files.

### Verification for this update

The focused quiz/content-governance run discovered **27 tests: 26 passed, 1 SQLite concurrency test skipped**. `manage.py check` and `makemigrations --check --dry-run` passed. The complete Marian backend suite discovered **1,291 tests: 1,289 passed, 2 skipped**. The final Activity 20 runner completed successfully: isolation tests **2/2**, Activity 18–19 focus **3/3**, learning-domain suite **195 discovered / 193 passed / 2 skipped**, backup/restore rehearsal passed, frontend tests **18/18**, lint **0 errors / 79 existing warnings**, and Vite build passed. SQLite cannot implement `SELECT FOR UPDATE`; both skipped tests remain for isolated PostgreSQL verification. No production DB was migrated or touched; provider credentials were removed from every check subprocess.

The delivery remains a source/staging candidate, not a production certification. Existing Marian marks, examination, publication, reporting, billing, migration, and finance code paths were not altered by this activity. See the canonical roadmap and `activity20-release-readiness.md` for the remaining owner, policy, provider, PostgreSQL, real-device, retention, and deployment gates.

## Content Studio Stage 1 - 19 November 2026 (curator role, platform-wide authoring, licence check)

Branch `feature/content-studio-stage1`, not merged to main. Added the `LearningContentRole` model (roles `author` and `curator`, active flag, granted by, granted at) with additive migration `0013_learningcontentrole`. Only a superuser can grant a role and each grant is audit-logged. Superuser and `is_staff` get no implied authority.

Added `MarianContentAuthor` and `MarianContentCurator` permissions and platform-wide endpoints in `platform_api.py`, separate from the school Studio endpoints. Authors create, edit and submit platform content (`scope="public"`, no school). Only curators review it, and a reviewer cannot be the author. Drafts are visible only to their author.

Added a licence check at submit: CC BY-NC and CC BY-ND are rejected, Public Domain/CC0, CC BY and CC BY-SA are accepted, and any other licence needs a recorded permission note in rights notes.

The publication gate (`PUBLICATION_POLICY_APPROVED = False`) is unchanged and publish still returns 503. No exam data was used. No AI provider is approved.

### Verification for this update

Learning-domain suite on the feature branch: 208 tests, OK, 2 skipped (Stage 0 baseline was 201). Frontend was not changed and was not re-run.
