# MARIAN SESSION 9 HANDOFF (started 4 Oct 2026)
Source of truth: MARIAN_CHANGE_PLAN.pdf (4 Oct 2026) + the actual code.
Older docs (HANDOFF.md, AI_CONTEXT.md) are partly stale. Update the PROGRESS LOG
at the bottom after EVERY commit+push.

## OWNER RULES (follow exactly)
- Owner works ONLY on a phone in GitHub Codespaces. ONE action per message.
- Pastes of 30 lines or fewer (cat > then cat >>). Give the exact folder.
- Ask for exact output (wc -l, "Ran N tests / OK", screenshot) before trusting success.
- Do not trust "no issue": a screenshot once showed FAILED when owner said no issue.
- ls before any mv or cat > on an existing file (a mv once wiped Login.jsx).
- git status --short before every commit. git add ONLY the files you wrote.
- Ignore hosting/paid plans. No real student data yet.
- Ranks/results: school admin + deputies only. Teachers/parents never see ranks.
- Deputy can do everything admin can EXCEPT appoint/remove deputies.
- NEVER BREAK: marks draft -> submitted -> approved -> locked. AI/analytics never
  change official records. Server-side permission checks only (hiding buttons is
  not security). Other school = 404, wrong role = 403, anonymous = 401.
- Additive migrations only, with defaults. Never reset the DB. Do not rewrite the
  app. No new libraries unless clearly needed.
- Every backend feature: model, migration, serializer, view, URL, permissions, tests.
- Backend tests (from backend/): export DJANGO_DEBUG=True; python manage.py test
  (about 5 min; all must stay green). Frontend: cd frontend; npm run build; npm run lint.

## STACK
Django 6.1 + DRF + SimpleJWT (backend/). React 19 + Vite, plain JSX, no router (frontend/).
Deployed on Render (practice only). Repo root: /workspaces/School.ai.platform.

## OWNER DECISIONS STILL NEEDED (ask one at a time)
1 Theme: keep black/gold or light. 2 Ranking when a student is missing marks: block
(recommended) with audited admin override. 3 Grading per school: CBC EE/ME/AE/BE,
8-4-4 letters, or both + boundaries. 4 Weights opener/mid/end (now equal).
5 Student/parent portals (not building). 6 PDF: browser print vs server PDF.

## BACKEND PLAN
P1 (B1 and B2 are DONE, see the DONE list):
B4 account mgmt: deactivate/reset teacher password, POST /api/schools/ + first admin
(superuser only), throttle change_password + blacklist refresh tokens.
B5 refresh token to HttpOnly cookie (late; CSRF/CORS care; test two-origin Render).
P2: B6 SchoolSettings (grading scale JSON, assessment weights, principal, motto, logo,
comment templates; GET/PATCH /api/school-settings/). B7 report cards: grades, weights,
ReportComment model, keep approved/locked only. B8 Student.status + POST /api/promotions/
(dry-run first, audited, never delete enrollments). B9 CSV import /api/students/import/
(?dry_run, atomic, size limit). B10 validate Subject.definition vs school curriculum.
P3: B11 audit filters+pagination+more events. B12 /api/search/. B13 /api/notifications/
(computed). B14 /api/approvals/summary/ (DB aggregation, flag 0/100/outliers).
B15 analytics: official vs draft separate. B16 /api/students/<id>/profile/ (no attendance).
P4: B17 indexes + select_related. B19 cleanup:
dead MAILERS, urls.py imports, students_api.py "if False" hack, split requirements,
HSTS later, stale docs. B20 GitHub Actions CI (tests + build + lint).

## FRONTEND PLAN
F1 theme tokens (ui.css). F2 app shell + hash routing (teachers see Home + Marks only).
F3 ui.jsx components (Input, Select, Modal, DataTable, Toast, ConfirmDialog, StatCard,
FilterBar, ErrorState, ErrorBoundary) + human error messages. F4 migrate screens, one
commit each. F5 admin dashboard (needs attention first). F6 teacher home. F7 Marks:
paper selector, autosave, paste-from-sheet, bulk absent. F8 Ctrl+K search + bell.
F9 login cleanup (fake remember-me/Google/Apple/Sign up). F10 mobile + accessibility,
compress login-pic.png (2.2 MB) to WebP. F11 offline marks. F12 reports/print. F13 vitest.

## KNOWN FACTS (do not rediscover)
- Performance is unique on (student, subject, academic_year, term, assessment_type,
  paper_number). Exam subject score = sum(paper marks x weight / 100); no SubjectPaper
  rows = one paper at 100%. Overall = plain mean of subjects. Rank = 1 + count strictly
  higher (ties share rank).
- Report card: subject average = mean of approved/locked marks; overall = mean of those.
- Early warning: average fell 10+ points since the previous published exam, or below 40.
- Deputy removal deletes the profile and deactivates the user.
- Login throttle 10/min per IP (needs DJANGO_NUM_PROXIES=1 behind a proxy).
- Lists: 50 per page, ?page_size up to 200. Teachers/deputies/audit are not paginated.
- Use listAll(path) from frontend/src/api.js for full lists (follows every page).
- Prefix CSS classes (mu-). No CSS animation on an SVG element with a transform attr.
- After B1: a teacher with NO TeacherAssignment sees nothing. Tests that need teacher
  reads must create a TeacherAssignment AND an Enrollment of the student in that stream.
- Phase 1 ui.jsx / ui.css / Marks.jsx rewrite were NOT in the repo (F1-F3, F7 redo them).

## DONE (committed and pushed). Test baseline: 182 tests, all OK.
- Frontend: listAll() in api.js; 8 screens load every page (no 200-row cap).
- exam_publish: exam row locked, so a concurrent publish returns 409.
- B1 teacher scoping: permissions.py is_teacher_only + restrict_for_teacher, applied in
  views.py (_list, performance_list), admin_edit._find, report_cards. A teacher sees only
  streams/subjects they are assigned (else 404). Tests: api/test_teacher_scope.py.
- B18: settings.py uses a fast hasher only when "test" is in sys.argv.
- B2 fair ranking: see OWNER DECISIONS MADE. Files: api/exam_publish.py,
  api/ranking_checks.py, api/test_publish_fairness.py.
- B3 Django admin guard (schools/admin.py): locked Performance and published Exam cannot
  be changed or deleted in admin; ExamResult is read-only (no add/change/delete); other
  admin edits/deletes are logged (audit actions admin_edit/admin_create/admin_delete).
  Side effect: students/schools with locked marks or results cannot be deleted in admin.
  Tests: api/test_admin_audit.py.

## NEXT (in order)
B20 CI (GitHub Actions: backend tests + npm build + lint), then B4 account management,
B11/B14, and F1-F3 (theme, app shell, ui.jsx). Follow the plan's 8-week order.

## CHECK LATER (teachers may still read too much)
dashboard, analytics, progress, early warning, exam results, mine.

## OWNER DECISIONS MADE
DECISION 2 (4 Oct 2026) ranking with missing marks - IMPLEMENTED in B2:
- Student has SOME marks but lacks a subject assigned to their stream: publish is
  BLOCKED (409) and the admin sees the student + missing subjects. The teacher must
  enter at least 1 (1 = absent) for each missed subject; it counts in the overall like
  any other mark. There is NO override flag.
- Student has NO marks at all: NOT blocked. Excluded from ranks and class overall.
  Listed in the publish response (not_ranked) and the audit log (action publish,
  details.not_ranked). TODO B13: notify admin + deputies. TODO B7: report cards and
  newsletters must show "did not sit" (derive: enrolled, no ExamResult in published exam).
- OPEN QUESTION for owner: reject a mark of 0 (minimum 1)? Model still allows 0-100.
TEST CONVENTION: in new test files use "from . import tests as base" and base.XTests.
Never "from .tests import XTests" (the runner would run those classes again).
Test baseline now: 179 tests.

## OPEN QUESTIONS FOR OWNER (ask one at a time)
- Reject a mark of 0 (minimum 1)? Model still allows 0-100.
- Decisions 1, 3, 4, 5, 6 above are still open (theme, grading, weights, portals, PDF).

## HOW THIS SESSION WORKED (for the next AI)
- Owner pastes blocks of 30 lines or fewer into the Codespaces terminal and sends a
  screenshot. Read the screenshot carefully: "no issue" was wrong once (FAILED).
- Every step was tested before commit. Verify with "Ran N tests / OK" from the real output.
