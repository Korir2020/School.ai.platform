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

## PROGRESS LOG
- B20 DONE (4 Oct 2026, commit 63169b1): .github/workflows/ci.yml, two jobs.
  backend: Python 3.12, requirements-prod.txt, DJANGO_DEBUG=True, manage.py test.
  frontend: Node 22, npm ci, build, lint. First run green: Ran 182 tests, OK.
- B4 parts 1-3 DONE (4 Oct 2026). Test baseline now 199, CI green on each push.
  Part 1 (cedec75, then 1b): api/teacher_accounts.py. PATCH /api/teachers/<id>/
  {is_active: bool}; POST /api/teachers/<id>/reset-password/ {password}. Admin or
  deputy, own school only (other school 404, teacher 403). Audited (teacher_activated,
  teacher_deactivated, teacher_password_reset). Reset blacklists that teacher's
  refresh tokens. GET /api/teachers/ now returns is_active.
  Part 2: api/password_throttle.py. change-password 5/min per user (1000 in tests).
  Part 3: api/session_cleanup.py end_other_sessions(). change-password signs out the
  other devices and keeps this one when the body has "refresh" (Password.jsx sends
  it). Missing, invalid or foreign token = every session signed out. Owner delegated
  this choice ("you know better").
- B4 STILL TO DO: POST /api/schools/ + first admin (superuser only).
- GAP: no password reset for school admins or deputies (teachers only). A forgotten
  admin password needs a superuser in Django admin. Consider deputy reset by the
  school admin, plus a superuser reset endpoint.
- Frontend not wired yet: no UI for teacher deactivate or reset (F-series).
- HANDOFF.md (old doc) had uncommitted edits from before this session; not touched.
- Workflow that worked: new file guard [ ! -e f ] && cat > f; sed edits guarded by a
  wc -l check; verify CI with gh run list and gh run view <id> --log | grep Ran.
- The "NEXT (in order)" section above is OUTDATED. Real NEXT: POST /api/schools/
  (B4), then B11/B14, B5, F1-F3.

## SESSION 9, LATER PART (5 Oct 2026). Test baseline: 229, all OK.
- B4 COMPLETE: POST /api/schools/ makes a school + first admin (superuser only,
  api/school_create.py). Admin/deputy password recovery: GET /api/admin-accounts/,
  POST /api/admin-accounts/<id>/reset-password/ (api/admin_accounts.py).
- B11 DONE: /api/audit-logs/ filters (api/audit.py, test_audit_filters.py).
- B14 DONE: GET /api/approvals/summary/ with flags (api/approvals_summary.py).
- FRONTEND DONE: Platform.jsx (Schools tab), Accounts.jsx (Admins tab), buttons on
  Teachers and Deputies, smaller login picture, forgot-password text.
- B5 DONE AND LIVE (refresh token in an HttpOnly cookie). Commits f86c727, f1ffd0c,
  8baf565, 10eac6f. Checked on the phone: login, reload, logout all work.
  * Render static site "Marian-app" has a Rewrite rule /api/* -> backend /api/*, so
    app and API are ONE origin. Needed because both *.onrender.com sites are
    cross-site (onrender.com is on the Public Suffix List): a SameSite=None cookie
    would be blocked by Safari/Brave. VITE_API_URL is DELETED in Render (do not re-add).
  * Cookie marian_rt: HttpOnly, Secure (not DEBUG), SameSite=Lax, Path=/api/auth/,
    7 days. api/auth_cookie.py: CookieLoginView, CookieRefreshView (reads cookie or
    body), put_cookie(), origin_ok().
  * CSRF: refresh and logout reject a foreign Origin (403) when the token comes from
    the cookie. Allowed: DJANGO_CORS_ORIGINS, DJANGO_CSRF_TRUSTED_ORIGINS, own host.
  * Logout reads the cookie and clears it (api/auth_logout.py). Change-password keeps
    the cookie's session and signs out the others (api/auth_password.py).
  * settings.REFRESH_IN_BODY: False in production, so login/refresh JSON has NO
    refresh token (cookie only). True while running tests (or DJANGO_REFRESH_IN_BODY=
    True). Tests: test_auth_cookie, test_cookie_session, test_cookie_prod.
  * Test gotcha: the test client now keeps the cookie, so tests that mean "no token"
    must call self.client.cookies.clear() first.
  * Frontend: api.js keeps the access token in memory only; localStorage holds just
    the flag "in" (signed in). Only ONE refresh call runs at a time (rotation +
    blacklist would sign the user out if two raced). Old "access"/"refresh" keys are
    removed on load. Password.jsx no longer sends the token. vite.config.js removes
    the Origin header in dev only.
  * If login ever shows "Failed to execute 'json'": VITE_API_URL was re-added or the
    Render rewrite rule is missing.
- NOT YET CHECKED (B5 follow-ups): a live curl proving the login JSON has no
  "refresh"; what the user sees when the 7-day session expires (should be login).
- NEXT: F1-F3 (theme + ui.jsx components), then B12, B13, B15-B17, B19.
- PHONE TIPS: lines over ~100 chars get cut when copied; never paste "read -s"
  (it swallows the next line): type "read -s P" by hand instead.
