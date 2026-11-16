# MARIAN PERSONALIZED LEARNING

## Technical Architecture Blueprint — Design Activity

**Status:** Approved design reference. Activities 3–14 have implemented the additive learning domain, role/tenant-scoped learner and staff APIs, learner screens, school-scoped content governance, fail-closed private asset APIs, and the Activity 11 account-operation core. Activities 18–20 add motivation/accessibility, aggregate analytics, encrypted offline learning, and source-copy release-readiness evidence. Activity 15 is implemented as a deterministic, explainable, learner-controlled recommendation service; it uses only permitted learning signals and rechecks live catalogue age, tenant, publication, language and entitlement rules. Activity 17 now contains the first partial feature slice: human-authored, independently reviewed, server-scored practice quizzes with answer-key isolation; coding, simulations, project workflows and path completion remain unimplemented. Activity 11’s approved age policy is documented and enforced, but provider-backed registration/contact-age-guardian verification, message delivery, recovery orchestration, retention execution, and moderator-case workflows remain disabled/incomplete. Activity 10 production use is separately gated on an approved durable private storage backend (with explicit `is_private=True` and `is_durable=True` declarations), malware scanner, and retention/audit policy; Activity 9 publication remains blocked pending separate policy approval. AI tutoring remains unavailable and disabled. The Activity 20 local runner now strips inherited database/provider credentials and uses a temporary SQLite test database; it is not production certification. See `personalized-learning-implementation-status.md` and the canonical roadmap for exact boundaries and verification.

## 1. Architecture decisions

1. Implement Personalized Learning as a bounded Django domain/app, provisionally `learning`, with learning-owned models, migrations, services, API URL module, permissions and tests. Keep operational `schools` and `api` models and workflows authoritative and unchanged.
2. Reuse Marian authentication and school/student/curriculum references through a small integration boundary. Never let a browser-supplied school or student ID establish authority.
3. Separate school-linked learning profiles from independent public learner profiles in the database and authorization rules. A user’s role comes from server-validated membership/profile records, never a client-supplied role.
4. Start with a curated, reviewable resource catalogue and deterministic recommendations. Add generative AI only behind a provider-neutral server gateway after provider approval, privacy controls, safety review, and cost limits exist.
5. No examination marks, academic weaknesses, report-card data, fee billing, or portfolios enter Personalized Learning recommendation inputs. No certificates in the initial product. Full offline learning is later work and is not supported by this blueprint as an existing feature.
6. Preserve existing API endpoints, hash navigation, database records, calculations, publication workflows, billing, and student-management behavior. Integrate using additive routes, tables, and feature flags.

## 2. Logical components

### Backend

- `learning.models`: learning-owned persistence and constraints.
- `learning.services`: publication, enrollment/linking, authorization-aware queries, progress ingestion, recommendations, and AI orchestration.
- `learning.permissions`: deny-by-default role and scope checks; tenant-scoped query helpers.
- `learning.api`: thin DRF views/serializers, separated into learner, teacher and administration URL modules.
- `learning.content`: safe external-resource metadata validation and private-file abstraction.
- `learning.ai`: provider interface, policy/validation middleware, quota reservation, redacted telemetry, and provider adapters.

### Frontend

- `LearningApp`: independently composed learning shell and URL-addressable learner/teacher/learning-admin areas; shared Marian design tokens and UI primitives are reusable.
- Learner home: discovery, continue learning, paths, interests/preferences, goals, saved items, progress and feedback.
- Teacher Studio: personal development, reviewed authoring, programmes and recommendations to explicitly authorized students.
- Learning Administration Centre: school settings, resource approval, user learning access, age controls, and aggregate usage/safety monitoring.
- Public learners use the learning surface without school-only menus or data. Do not make a public account look like a school tenant.

### Data and external services

- Relational learning records live in the new learning domain, with FKs to Marian `User`, `School`, `Student`, `TeacherProfile`, guardian relationships, and curriculum reference models only where applicable.
- Learning-resource binaries use `LearningPrivateAsset` metadata plus `learning.asset_storage`; store an opaque storage key, checksum and scan state—not large file bytes in learning database rows. Development filesystem storage is outside `MEDIA_ROOT`; production has no local fallback and fails closed until an explicitly configured backend implementing `save/open/delete` declares itself private and durable. No public `/media/` URL is authority to view learner content.
- External resources are links/metadata unless licensed storage and redistribution rights are explicitly documented. The application must not scrape restricted sites or fetch user-supplied URLs server-side without SSRF defenses.

## 3. Initial data model proposal

| Model | Core fields and constraints | Purpose |
|---|---|---|
| `LearningProfile` | OneToOne `user`; `scope` (`school`/`public`); nullable `school`; nullable OneToOne `student`; locale; age band; created/updated; consent state. Check constraints enforce public profiles have no school/student and school learner profiles have a matching school/student. | Learner preferences and learning ownership. School staff use existing role profiles; an optional learning profile stores their preferences without duplicating their staff role. |
| `LearningInvitation` | Student FK, school FK, created_by FK, hashed one-time token, created/expiry/claimed times, guardian approval state/actor/time, revoked time; unique active invite per student. | School-admin-issued, expiring student account claim. Raw tokens are returned once and never persisted. Guardian confirmation is required for minors before activation. |
| `LearningFramework` | Name, code, region, version, active flag. | Configurable CBC, Cambridge, and future framework reference. |
| `LearningTopic` | Framework nullable FK, parent topic, code, multilingual labels, grade/age bands, subject/topic type, active flag. Unique code within framework/version. | Configurable curriculum and general-knowledge taxonomy; no grade assumptions embedded in application logic. |
| `LearningResource` | Owner/school scope, title/summary/body, format, origin (`Marian`/`external`), HTTPS URL or legacy storage marker, language, difficulty, age range, topic links, curriculum alignment, licence/attribution, author, version, moderation state, published/retired times. | Governed content catalogue. Only approved/licensed, published content is learner-visible. |
| `LearningPrivateAsset` | Resource FK, opaque private storage name, content type, byte size, SHA-256, quarantine/clean/infected/deleted state, uploader, scan/deletion timestamps. | Attachment lifecycle metadata; bytes remain in private storage and a clean scan is required for access or content submission. |
| `LearningResourceTranslation` | Parent resource/version, language, translated fields, translator/source, human-review state, created time. | Keeps original content distinct from translations and permits reviewed updates. |
| `LearningPath` | Owner/scope, title, description, audience/age range, language, difficulty, objectives, curated/teacher/AI origin, state, author, version. | Structured courses, interest pathways, career/skills journeys and professional development. |
| `LearningPathItem` | Path FK, resource/activity FK, sequence, prerequisite items, completion rule. Unique sequence/resource policy within a path version. | Ordered lessons and activities. |
| `LearningPreference` | OneToOne profile, selected topic IDs, preferred formats/languages/difficulty, recommendation opt-out, updated time. | Editable learner preferences; no examination data. |
| `LearningGoal` | Profile FK, title, description, target date optional, linked topic/path, state, created/updated. | Personal learning goals that users may edit or close. |
| `SavedLearningItem` | Profile FK, resource/path FK, saved time; unique profile/item. | Saved library. |
| `LearningActivityEvent` | Profile FK, resource/path-item FK, event type, occurred time, bounded JSON details, client-generated idempotency key, source/version. Append-only for meaningful activity; indexed by profile/time. | Starts, attempts, submitted work and completions—not clicks or time-only rewards. |
| `LearningProject` | Owner profile, optional school cohort, title, objective, age band, topic, stage template, review state. | Guided personal/project-based learning. |
| `LearningProjectWork` | Project/profile FK, stage, typed submission or private file key, review/feedback, timestamps. | Learner-created work and teacher guidance with explicit ownership. |
| `LearningRecommendation` | Profile FK, content/path FK, reason code, explanation, source inputs limited to opted-in learning preferences/activity, algorithm/provider version, created/expiry, state (`shown`, `accepted`, `dismissed`). | Explainable, dismissible suggestions; no profiling from exam weaknesses. |
| `AIInteraction` | Profile FK, purpose, provider/model, policy version, request/result state, bounded token/cost counters, latency, redacted request ID, created time. Never store raw prompt by default. | Rate/cost telemetry, abuse control, auditability without unnecessary learner data. |
| `LearningAuditEvent` | Actor, school/scope, action, target type/id, timestamp, redacted details. | Audit privileged content moderation, invitation/consent actions, exports and access changes. |

### Data integrity rules

- A school-scoped resource/path is visible only within its school unless a platform-level moderator publishes a shared catalogue version. Public content and private school content have explicit scopes; neither is inferred from null fields alone.
- Profile/student/school consistency is checked in services and database constraints where supported. A linked student must be active or explicitly granted an allowed alumni state; transferred students lose the former school’s live learning access.
- Student account linking is one-to-one and invitation-based. A reused, expired, revoked, or mismatched token never links an account. No endpoint accepts a client-chosen student/school to claim identity.
- Approved age policy: under 10 is school-managed only; ages 10–17 require verified guardian involvement and consent for independent access; ages 18+ may self-register after actual age/contact verification; unknown age cannot use protected learning features. The independent minimum defaults to 10 and configuration cannot lower it. Under-18 protected access requires verified guardian consent; invitation approval alone is not age verification. If real email/SMS, age, or guardian verification is unavailable, provider-dependent registration and verification remain disabled.
- Deletion and retention are lifecycle operations with audit/history rules; do not cascade-delete official Marian student records when a learning account is removed. Provide a documented account unlink/export/delete process.
- Activity payloads have schema/size limits, no arbitrary executable HTML, no sensitive exam values, and no unrestricted client-supplied metadata.

## 4. API boundary proposal

Prefix: `/api/learning/v1/`. All endpoints use Marian authentication except deliberately public registration/claim endpoints, which require strict throttling and anti-enumeration behavior. School/public scope is inferred from the authenticated learning profile and existing memberships.

| API | Methods | Authorization/behavior |
|---|---|---|
| `/me/` | GET, PATCH | Authenticated learning user; return only own profile and preferences. Server controls scope, school, linked student and role. |
| `/accounts/capabilities/` | GET | Public, truthful provider capability state and approved minimum age; no provider credentials are exposed. |
| `/accounts/register/` | POST | Public and throttled; currently always returns 503 and creates no profile or Marian user. |
| `/account/lifecycle-requests/` | GET, POST | Own lifecycle history or non-destructive suspension/deletion request; protected learning access is restricted, but permanent deletion is not performed. |
| `/account/lifecycle-requests/{id}/cancel/` | POST | Requesting user cancels their own pending request; audit event records the state change. |
| `/guardians/learners/` | GET | Authenticated linked Marian guardians receive minimal linked-learner summaries; access is audited and ineligible learner progress is suppressed. |
| `/guardians/learners/{id}/consent/withdraw/` | POST | Linked guardian withdraws consent; protected learning access is blocked. New verified consent capture is not implemented. |
| `/teachers/learners/{id}/summary/` | GET | Assigned teachers receive minimal eligible progress aggregates only; no conversation text. |
| `/admin/learning-summary/`, `/admin/learning-accounts/` | GET | Full school administrator only; school-local aggregate/list, bounded at 200 rows, audited; no independent public profiles. |
| `/admin/learning-accounts/{id}/state/` | POST | Full school administrator may suspend/reactivate own-school learning access; existing age/consent gates still apply. |
| `/invitations/claim/` | POST | Redeem an expiring invitation after required guardian approval; one-time transaction creates/link user and profile. Generic failures prevent student enumeration. |
| `/catalog/` | GET | Authenticated users; published content only, filtered by locale, topic, framework, difficulty, age suitability, format, and visibility. Queryset constrains scope. |
| `/resources/{id}/` | GET | Published and in-scope resource only; validates age/scope and authorized private-file access. |
| `/saved/` | GET, POST, DELETE | Own profile’s saved items only; POST/DELETE use exactly one `resource_id` or `path_id`; create/remove are idempotent. Lists are bounded and recheck current catalogue publication, language, age, licence, and tenant visibility so stale/hidden items are not returned. |
| `/saved/{id}/` | DELETE | Remove one caller-owned saved record; records belonging to another learner are concealed with 404. |
| `/goals/` | GET, POST, PATCH, DELETE | Own goals; teacher visibility is separate and requires a recommendation/assignment permission. |
| `/paths/` and `/paths/{id}/` | GET | Published/in-scope paths and ordered items, personalized only from allowed inputs. |
| `/activity-events/` | GET, POST | Own learner history only. POST accepts bounded, schema-validated, idempotent self-assessment events against a currently visible resource/path item. No client completion claim is accepted, and no completion rule is yet verified against learning outcomes; participation remains in progress. |
| `/recommendations/` | GET; `/{id}/feedback/` POST | Own recommendations only; return reason and user control. Dismissal/feedback is persisted. |
| `/projects/` | GET, POST; `/projects/{id}/work/` POST | Owner-scoped projects and submissions; teacher review requires an explicit authorized relationship. |
| `/teacher/resources/` | GET, POST, PATCH | Teacher’s own drafts and authorized school content; submit for review, cannot self-approve school-wide content unless policy explicitly grants moderator role. |
| `/teacher/learners/{id}/recommendations/` | GET, POST | Teacher only for learners within assigned classes/streams; record recommending actor and school. Never grants teacher ownership of learner account. |
| `/admin/resources/` | GET, POST, PATCH | Full school admin sees/moderates only that school’s resources; platform moderator manages global catalogue separately. |
| `/admin/invitations/` | GET, POST, revoke | Full school admin only, own-school roster. Raw one-time token is returned once for manual secure handoff; no message is sent. Expired invitations may be retired before a fresh token is issued. Resend remains a no-send 503 until a real provider is integrated. |
| `/admin/usage/` | GET | Aggregated, minimum-necessary school usage; no private conversation text. School admin sees only school totals and their own learning settings. |
| `/ai/tutor/sessions/` | POST | Only when provider, privacy, safety and quota settings are active; otherwise returns explicit `503 ai_not_configured`. No fake response. |
| `/ai/content-drafts/` | POST | Teacher/authorized author only, review state is `draft`; never publishes generated content automatically. |
| `/ai/translate/` | POST | Authorized author, source and translation kept separate; important curriculum translations require human approval. |

Error responses must not disclose whether a learner, invitation, or resource exists outside the caller’s scope. Use pagination, bounded filters, rate limits, audit logs for privileged actions, and CSRF/session behavior consistent with existing Marian auth.

## 5. Permission matrix

| Capability | Public adult learner | School learner | Teacher | Full school administrator | Learning moderator/platform operator |
|---|---:|---:|---:|---:|---:|
| Discover approved shared resources | Yes | Yes | Yes | Yes | Yes |
| Read private school resource | No | Own school only | Own school/authorized class | Own school | Only explicit platform moderation need |
| Read/edit own goals, interests, saves, learning history | Own only | Own only | Own only | Own only | No routine access to private learner history |
| Invite/link a student | No | No | No by default | Own school roster only | Exception workflow only, audited |
| See learner-specific activity | Own only | Own only | Assigned learners and purpose-limited | Limited school oversight/aggregate by default | Restricted, audited support access |
| Create a personal learning path/project | Own scope | Own scope | Own drafts | Own scope | Shared catalogue policy |
| Publish shared content | No | No | No | School scope after review | Global catalogue after review |
| Manage school settings/usage | No | No | No | Own school only | Platform configuration, audited |
| See or change other school/public private data | No | No | No | No | Only narrowly authorized, audited operations |
| Use AI | Opt-in, age policy, quota | Opt-in, guardian/age safeguards, quota | Authorized use with learner privacy | Authorized author/admin use, quota | No default exemption from controls |

A user's Marian job role does not restrict their ability to learn or explore topics. It only governs administrative actions and access to other people's data. Deputies and limited school staff are not full school administrators unless a reviewed permission explicitly grants the relevant learning action.

## 6. AI and safety design

- Define an `AIProvider` interface (`generate_structured`, `translate`, `health_check`) and independently test providers through adapters. Select an allowlisted provider/model in server configuration; keep credentials in deployment secrets only.
- Default to **disabled** until a provider is approved, credentialed, privacy-reviewed and configured. User interface must show the disabled state accurately.
- Send pseudonymous learner context only when necessary; avoid names, school identifiers, admission numbers, exact birth dates and unrelated academic records. Do not use examination marks, report text, or weakness labels for personalization.
- Add policy version, age band, permitted task, per-user/tenant/global token and cost quotas, concurrency-safe quota reservation, timeouts, bounded retries, output schema checks, moderation and safe failure. Log model, policy version, redacted request ID, latency and cost, not raw prompts by default.
- Treat learner messages and external-resource content as untrusted. Guard against prompt injection, harmful instructions, data leakage and unsupported claims. Cite approved content or explain uncertainty; allow the user to dismiss feedback.
- Require teacher/editor review for publishable generated lessons, quizzes, projects and curriculum material. The model cannot publish, assign to a child, change official Marian records, or make high-impact/diagnostic decisions.
- Define guardian controls, age-appropriate policies, report/block/escalation paths, retention and deletion before a child-facing AI pilot. Provider data-processing/retention terms require product-owner approval.

## 7. Search, recommendations and localization

- Search only approved catalogue records and index public metadata plus content the user is authorized to see. Search filters include topic, curriculum/framework, grade/age, language, difficulty, format and content origin.
- Initial recommendations are deterministic and explainable: match user-selected interests, goals, language, chosen difficulty, opted-in format preferences, and recent learning-path/activity events. No exam analytics, academic risk scores, hidden traits, or opaque profiling.
- Store reason codes and source signals; let users dismiss, edit preferences, pause recommendations, and inspect why an item was suggested. Keep recommendation event history bounded and governed by retention policy.
- Use a translation catalog for all interface text with English and Kiswahili entries from the start. Search language-aware metadata; treat machine translation as draft and preserve original text, translator/source, version, and human-review status.

## 8. Security, privacy, and operational controls

- Deny by default; constrain querysets by scope before object lookup. Add cross-school/public-vs-school negative tests for every endpoint and tenant-bearing FK. Recheck identity and active student/teacher/guardian relation on each request.
- Enforce upload allowlists, byte/pixel/dimension limits, content decoding, malware scanning/quarantine, archive-bomb protections, rate/tenant quotas, private storage, authorized download views, safe content disposition and `nosniff`. Activity 10 provides these controls for school learning-resource attachments; it accepts only PDF/JPEG/PNG, normalizes images/PDFs, rejects unsupported archives, and keeps uploads inaccessible until a configured scanner reports clean. Production upload intentionally returns unavailable until an explicitly configured private-and-durable backend exists. Deletion revokes access before physical cleanup; published content must be archived by a full school administrator before attachment deletion. Physical cleanup is retryable and no automatic retention interval is assumed.
- Use explicit retention periods and user/guardian access, export, correction, unlink and deletion processes. Keep minimized audit events for moderation, account linking, consent, exports and AI usage. Restrict raw learner conversations; provide no routine school-admin transcript access.
- No offline learner content/progress in this design phase. Future offline work needs encrypted local storage, device identity/revocation, content rights/offline licensing, expiry, sync idempotency, conflict resolution, and explicit threat-model tests.
- Before production, verify PostgreSQL migrations, backups/restore, object storage permissions, email verification, guardian consent process, secrets, CORS/CSRF, throttles, logs, incident response, child safety and provider contracts.

## 9. Migration and compatibility plan

1. Add the `learning` app and additive migrations only. Do not change or backfill existing official academic/fee data. Existing students remain without learning accounts until invited and consent/link rules are satisfied.
2. Add feature flags for public signup, student claims, AI, teacher publishing and moderator workflows. Default external AI and public minor registration off until verified dependencies are operational.
3. Add routes under `/api/learning/v1/`; do not repurpose existing `/api/` academic endpoints. Add learner role resolution to `/api/auth/me/` only after the student account model and tests are ready; avoid changing role precedence for existing users.
4. Add the learning interface as an independently mounted route/shell while preserving existing hash-tab URLs and navigation. Confirm routing and refresh fallback in the actual deployment before enabling direct routes.
5. Test migrations on a copied SQLite development DB and production-like PostgreSQL; verify that original Marian records and exam/report outputs are unchanged. Include rollback/forward-fix guidance and backup rehearsal.

## 10. Implementation gates and acceptance

### Gate A — Identity and isolation

- Documented role matrix approved; public adult verification and guardian/consent flow approved.
- Tests prove no cross-school, unassigned-teacher, unlinked-guardian, public/school or identifier-tampering access.
- Existing auth/login/recovery and role resolution regression tests pass.

### Gate B — Content and learner MVP

- Approved resource catalogue, curriculum/topic configuration, language metadata and private file lifecycle operate end to end.
- Learner can set interests/goals, search approved resources, save items, follow a path and record validated progress.
- Teacher and school admin actions are scoped and audited; public learner records remain isolated.

### Gate C — AI pilot

- Provider approval/configuration, safety review, data minimization, moderation, cost quotas, evaluation set, failure behavior and deletion/retention policies are demonstrated.
- AI endpoints fail closed when disabled; no frontend key, fake output, or automatic publication.

### Gate D — Rollout and expansion

- Responsive/accessibility/localization acceptance tests pass; English and Kiswahili are user-selectable and reviewed.
- Full existing Marian test suite, new learning security tests, production-like migration tests and rollback rehearsals pass.
- Offline support, certificates, live external-service dependencies, and any unverified capability remain clearly marked unavailable until implemented and tested.

## 11. Decisions still requiring product-owner approval

- School-managed student account creation, guardian identity/consent verification, and policy for missing/unknown date of birth.
- Public account age threshold, email-verification dependency, and public-minor/guardian account lifecycle.
- Resource licensing allowlist, content moderation standards, content retention/deletion, and school-vs-global catalogue ownership.
- AI provider(s), provider contracts/data retention, usage budgets, age-appropriate policy, and whether tutor transcripts are retained.
- What learner-specific activity teachers and school administrators may see, and for what educational purpose.
- Product-admin/moderator access and escalation, analytics aggregation/retention, public-content quality assurance, and deployment storage/email requirements.

These are gates: when not approved/configured, the relevant feature must remain unavailable rather than relying on silent assumptions.
