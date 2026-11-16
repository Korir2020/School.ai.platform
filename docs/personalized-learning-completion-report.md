# Marian Personalized Learning
## Requirements and Feature Completion Report — Updated

**Updated:** 16 November 2026
**Project source:** the independent copy extracted from the uploaded Activities 18–20 archive. The uploaded ZIPs and primary Marian repository remain untouched.

## Executive summary

Marian Personalized Learning is a separate, self-directed learning ecosystem inside the Marian platform. It is not an extension of examinations, marks, reports, attendance, risk analytics, billing, or school administration. It must serve school-linked and independent learners, while also supporting teachers and administrators as learners, under separate identities and permissions.

The project already contains the separate Django `learning` domain, additive migrations, account and guardian foundations, learner APIs and screens, catalogue/content-governance services, teacher/admin experiences, deterministic recommendations, motivation/accessibility/analytics foundations, and offline-learning groundwork. This implementation pass added the first genuine Activity 17 learning interaction: educator-authored, reviewed, server-scored multiple-choice practice quizzes. It also hardened the Activity 20 local release-readiness runner so test subprocesses cannot inherit database or provider credentials and use only a temporary SQLite test database.

**The product remains partial and is not production-ready.** Quizzes are not published, because the existing rights/moderation/shared-catalogue policy gate is still closed. The broad project studio, AI tutor, automatic access for eligible existing Marian students, real account verification/delivery, production storage/scanning, premium payment, PostgreSQL concurrency evidence, and operational/device release tests remain incomplete or gated.

## Confirmed product requirements

Keep the learning domain and public accounts independent from official school operations. Public learners remain tenantless; school-linked learners must be linked only through a trusted server-side relationship. Do not use or modify examination marks/calculations, report cards or archives, attendance, fees, risk scores, migration records, or existing school-administration workflows to personalize or assess learning. Preserve Marian login, roles, navigation, billing, and existing records.

Support students, public learners, teachers, administrators, guardians in limited child-safety roles, and platform super-administrators without giving their permissions to one another. Users may explore learning outside their job role, but school-content, account, guardian, and learner-data access remains least-privilege and server-enforced. A school administrator is limited to their own school; deputies and ordinary staff do not inherit full-admin authority; teachers are restricted to their own school content and assigned learners; guardians to their linked children; learners to their own profile, preferences, goals, work, and learning history.

Prioritize English and Kiswahili and provide age-appropriate, mobile-first, accessible learning. Curriculum configuration must support Kenyan CBC Grades 1–12, Cambridge, international frameworks, and non-curriculum learning. Broader learning topics include technology/programming, robotics, science, business, financial literacy, languages, leadership, creativity, research, history/geography, agriculture/environment, health education, life skills, professional development, and general/global knowledge.

Existing active Marian students should receive learning access through existing accounts, without a redundant invitation when a trusted account-to-student link can be verified. Independent registration follows the confirmed age policy: under 10 is school-managed only; ages 10–17 require verified guardian involvement and consent for independent access; adults may self-register only after real age/contact checks; unknown age is denied protected features. Provider-dependent verification, account recovery, guardian consent, and delivery must not be represented as active unless configured and tested.

Every eligible learner must ultimately have meaningful free content. Premium is an individual learner subscription, separate from school subscriptions and school-fee operations; a parent or guardian may pay for an eligible minor. Prices remain configurable until approved, and unverified payment responses never grant premium.

AI must be provider-independent, server-side, safety-reviewed, age-appropriate, privacy-minimizing, rate/cost-limited, auditable without logging sensitive content, and disabled until an approved provider, credentials, and policies exist. Publishable AI content requires human review. Interactive work must be real, secure, and private by default; completion must rely on server-verifiable evidence, not time-on-page, clicks, or arbitrary client claims.

## Canonical Activities 1–20: current status

| Activity | Status now | Notes |
| --- | --- | --- |
| 1. Product vision and architecture | Done | Product direction, audit and architecture references exist. |
| 2. Learning-domain data foundation | Done | Separate models and additive migrations exist. |
| 3. School-linked identity foundation | Partial | Invitation/claim and guardian-approval safe core exists; see Activity 11. |
| 4. Learner profile/preferences API | Done | Learner-owned, allowlisted API exists. |
| 5. Learner goals API | Done | Own-goal CRUD with scope checks exists. |
| 6. Read-only catalogue API | Done | Eligibility, language, age, review and scope checks exist. |
| 7. Saved items | Done | Learner-owned save/list/remove exists. |
| 8. Participation/progress | Partial | Safe events exist; quiz attempts now create server-owned completion evidence, but do not complete learning paths. PostgreSQL race tests remain. |
| 9. Content governance/publishing | Partial / gated | Draft, review, version and audit foundations exist; publication remains blocked pending rights, moderation and catalogue ownership approval. |
| 10. Private-file lifecycle | Implemented / deployment-gated | Production still needs an approved durable private store, scanner, monitoring and retention policy. |
| 11. Accounts and guardians | Partial / dependency-gated | Existing eligible Marian students still need trusted automatic access without unnecessary invitation. Real registration/verification/delivery, recovery, deletion and guardian-as-payer are not live. |
| 12. Learner experience | Implemented / content-gated | Learner UI exists; content, catalogue and some localization remain gated. |
| 13. Teacher Studio | Implemented / publishing-gated | Teacher workflows exist; publication is still blocked. |
| 14. Learning Administration Centre | Implemented / school-scoped | Admin centre exists without bypassing other gates. |
| 15. Recommendations | Implemented / content-and-entitlement-gated | Deterministic and explainable; not AI; avoids exam/academic weakness data. |
| 16. AI gateway | Not started / approval-gated | No provider, child-safety, privacy/retention, escalation or budget approval; do not fake AI. |
| 17. Interactive/project studio | **Partial** | Human-authored, versioned, server-scored MCQ quiz slice now exists. Coding, simulations, language practice, projects/submissions/feedback and path-completion policy remain. No new quiz is published. |
| 18. Motivation/accessibility/analytics | Implemented / operationally gated | Translation review, analytics retention/deletion and access review remain. |
| 19. Offline learning | Implemented / content-and-operations-gated | Rights, revocation, service-worker delivery, real-device and PostgreSQL tests remain. |
| 20. Release readiness | Local technical checks passed / production gates open | Runner hardened and passed locally; no production certification or deployment. PostgreSQL, backups, device, storage, policy and provider gates remain. |

The canonical activity sequence is `docs/personalized-learning-canonical-roadmap.md` inside the project ZIP; it supersedes historical numbering in older reports.

## Latest implementation delivered

The new additive migration `learning.0012_learningresource_practice_quiz_learningquizattempt` adds structured quiz content to learning resources and a private attempt record. Teacher Studio can author original quiz drafts, save answer-key revisions, and show a school-scoped answer-key preview to authorized independent reviewers. A draft must pass server validation before it can be submitted for review. Existing author/reviewer separation remains, and publication is still unavailable.

Learners can retrieve currently eligible questions without seeing answer keys or explanations. On submission, the server verifies ownership, profile/consent, school or public scope, current language/version, current catalogue visibility and access tier; rejects unknown/client-supplied score fields; calculates the outcome; and enforces UUID idempotency and a dedicated request throttle. The stored attempt does not contain selected answer IDs. A minimal owner-visible completion event records only validated quiz/resource-version evidence. It does not alter examination or report data, expose correctness to teachers, or complete a path step. Learner UI offers English/Kiswahili labels and clearly calls the result practice, not an exam mark or mastery certificate.

For Activity 20, `scripts/release_readiness.py` now launches checks using a minimal environment allowlist, replaces the development secret, strips inherited database/provider credentials and directs Django's test-only SQLite database into a temporary directory. Unit tests verify the credential filter. This changes neither the normal application DB choice nor PostgreSQL configuration. The local backup/restore rehearsal handles only temporary SQLite files.

## Verification actually completed

Django `check` passed and migration drift reported no changes. The focused quiz/content-governance run discovered **27 tests: 26 passed and 1 SQLite-only concurrency test skipped**. The complete Marian backend run discovered **1,291 tests: 1,289 passed, 2 skipped**. The hardened Activity 20 runner completed: environment-isolation tests **2/2**; Activity 18–19 focus tests **3/3**; learning-domain suite **195 discovered, 193 passed, 2 skipped**; disposable SQLite backup/restore rehearsal passed. Frontend unit tests passed **18/18**; lint reported **0 errors and 79 existing warnings**; the Vite production build passed, with its existing large-chunk advisory. The new quiz components had no lint diagnostics.

The two skipped concurrency tests require a database that implements `SELECT FOR UPDATE`; SQLite cannot run them. They still need verification on an isolated PostgreSQL test database. No production database was migrated or modified, no external AI/payment provider was contacted, no email/SMS was sent, and no content was published.

## Remaining work and safe completion sequence

1. **Close the Activity 11 existing-student access gap.** First identify a trusted server-side account-to-roster relationship. The inspected source did not justify inferring identity from name/email or accepting a client-supplied student/school ID. If no trusted mapping exists, define and implement an explicit safe linking operation; until then, do not auto-link. Test idempotency, active status, cross-school and guardian boundaries, and unchanged `/auth/me` roles and Marian operations.
2. **Resolve Activity 9 publication decisions.** Obtain approval for licensing/rights allowlists, moderation and reviewer rules, shared-catalogue ownership, and translation review. Then curate rights-cleared free learning content. Until approval, keep publish unavailable; without eligible published content, a free plan does not equal meaningful free learning access.
3. **Resolve Activity 10 production storage.** Choose and approve durable private storage, malware scanning, monitoring and retention/deletion policy; verify failed scans, outages, retry and controlled delivery.
4. **Extend Activity 8 progress safely.** Define verifiable outcomes and whether a quiz result may complete a particular path step. Add explicit reviewed linkage and keep current path state unchanged until that policy is tested. Never infer completion from client claims or time.
5. **Finish remaining Activity 11 lifecycle work only with real providers.** Registration, age/contact checks, guardian identity/consent, message delivery, recovery, retention/deletion and case-moderator workflows remain disabled until provider and privacy decisions and tests exist.
6. **Build Activity 16 only after approvals.** Select an AI provider and approve data processing/retention, child-safety, moderation/escalation, quota and budget. Implement a default-off provider gateway, secrets server-side, filtered context, rate/cost limits, safety/output validation, timeouts, redacted audit, and honest unavailable states. Never simulate an AI answer.
7. **Continue Activity 17 from the quiz slice.** Add other activities one at a time: exercises, math/science visualizations, coding inside an isolated sandbox, language practice, guided projects, safe private submissions and feedback. Decide attempt-data retention and staff visibility first. Keep learner content unpublished until Activity 9 allows it.
8. **Implement individual premium only after free content is meaningful.** Approve pricing/entitlements, guardian-as-payer policy and payment provider; verify signed/idempotent server events, failures, refunds, cancellation and expiry. Keep checkout disabled until approval and credentials exist. Do not connect this to school fees or school subscriptions.
9. **Complete Activity 20 staging/production evidence.** Run PostgreSQL concurrency tests on an isolated test DB; rehearse approved backup/restore/rollback; verify storage/scanning and retention; test account/guardian/tenant gates and incident response; and test Android/iOS keyboard, screen reader, contrast, reduced motion, offline expiry/revocation and sync. Only claim release after explicit owner approval and successful evidence.

## Definition of complete

The product is complete only when eligible users can access rights-cleared, age-appropriate learning; follow meaningful learner journeys; get safe and honest recommendations/AI assistance; complete interactive learning; control their learning data; and use free or individually paid learning under approved account, guardian, and payment rules—with server-side permission enforcement and evidenced production operations. The current source package and passing test suites alone do not constitute product completion.


## Delivery

The complete updated source package is **`Marian_Personalized_Learning_Full_Updated_Activity17_Activity20.zip`** (about 3.6 MB). It contains the full source/configuration tree from the uploaded Activities 18–20 package, plus the current Activity 17 quiz implementation, Activity 20 runner hardening, and updated roadmap/status reports. Three private job receipt PDFs found in the upload were deliberately excluded as private runtime artifacts; no original application source files were dropped. Database files, secrets, dependencies, generated frontend builds, caches, logs, and runtime private-job data are excluded. The archive passed ZIP integrity and required-file/exclusion checks; use the adjacent `.sha256` sidecar to verify the delivered archive.

This is a clean source/staging handoff, not a production deployment, database migration, publication, payment activation, or release certification.
