# Activity 17 — First usable practice-quiz slice

**Status: PARTIAL.** This delivers a real, non-AI quiz activity inside the existing Personalized Learning domain. It is not completion of the Interactive Learning Studio or Project Studio.

## Delivered

- Added an additive `LearningResource.practice_quiz` JSON field and `LearningQuizAttempt` model in migration `learning.0012_learningresource_practice_quiz_learningquizattempt`. Quiz structure is versioned and validated server-side. A quiz has at most 20 questions, 2–6 plain-text options per question, bounded prompts/options/explanations, unique IDs, and exactly one valid correct option. Incomplete interactive drafts can be saved, but cannot be submitted for review until all questions are complete.
- Extended Teacher Studio draft create/edit and immutable resource-revision snapshots. Teachers can author original practice questions, options, correct choices, and explanations. Authorized school reviewers receive a school-only answer-key preview as part of independent content review. Author self-approval remains denied. The existing publish route remains hard-gated; this change does not publish any content or enable a public catalogue.
- Added learner-only, version-bound routes:
  - `GET /api/learning/v1/practice/resources/<resource_id>/quiz/?lang=en|sw` returns the currently eligible quiz questions and options, never correct answers or explanations.
  - `POST /api/learning/v1/practice/resources/<resource_id>/attempts/` validates a strict answer envelope, required UUID idempotency key, current resource version and all question/option IDs. The server calculates correctness and explanations; client scores are rejected.
- Attempts are permitted only for the authenticated account’s eligible learning profile and a currently visible published quiz. Existing tenant, language, age, guardian-consent, school-suspension, licensing/publication, private-resource scope, and Free/Premium entitlement checks are reused. Both eligible school-linked learners and verified public adults are covered by tests; public profiles remain tenantless and cannot read school content. Attempts have a dedicated 20/hour user throttle.
- The server persists only the version, idempotency HMAC, aggregate correct/question counts, and post-attempt feedback; selected answer IDs are not stored. Exact retries return the original result; reuse of the same key with different answers conflicts. Learner-visible catalogue/detail serializers do not contain quiz keys. The attempt record is learner-private; teacher activity summaries do not reveal correctness or selected answers.
- A successful server-validated attempt creates one minimal owner-visible `completed` activity event with the quiz resource/version only. It does not change path participation state or mark a learning-path step complete. Outcomes are practice evidence, never Marian examination marks, report-card data, certificates, or claims of mastery.
- Added responsive learner interaction in English and Kiswahili, answer selection, validation, post-attempt feedback, and a clear non-exam/non-mark notice. No AI, code execution, external content fetch, or new provider is used.

## Verification evidence

- Django system check: passed; migration drift: no changes detected.
- Focused quiz API and content-governance suites: **27 tests discovered, 26 passed, 1 SQLite-only concurrency case skipped**.
- Full Marian backend suite on a disposable SQLite test database: **1,291 tests discovered, 1,289 passed, 2 skipped**. Both skipped tests require a backend supporting `SELECT FOR UPDATE` and need PostgreSQL verification.
- Activity 20 release runner: quiz-related checks are part of the **195-test learning-domain suite (193 passed, 2 skipped)**; the runner’s credential-isolation tests passed **2/2** and Activity 18–19 focused tests passed **3/3**.
- Frontend tests: **18/18 passed**. Lint: **0 errors, 79 warnings**, unchanged from the pre-existing baseline; no diagnostics were reported in the modified quiz components. Vite production build passed, with the existing large-chunk advisory.

## Limits and next work

Activity 17 remains incomplete. Current quizzes are bounded multiple-choice practice only. There is no quiz import or authoring AI, math visualization, simulation, sandboxed coding, language-practice engine, guided project workflow, learner work submission/review, or feedback workflow. No client event can claim quiz completion; only a successful server-scored attempt creates the minimal activity event. Paths remain in progress because the quiz has not been linked to path-step completion policy. The catalogue publication gate remains closed pending owner-approved licensing, moderation, reviewer, and shared-catalogue decisions, so no claim is made that eligible learners already have a populated, usable quiz catalogue.

Quiz outcome records and human-review visibility still require the product’s approved retention/access policy before production rollout. All server security checks remain authoritative even if UI controls are bypassed. No production database was migrated, and no external provider, payment or AI integration was contacted or enabled.