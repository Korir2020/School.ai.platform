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

## SESSION 9, UI REDESIGN PART (5 Oct 2026). READ THIS FIRST.
Branch: ui-redesign (NOT main). The zip of main is behind: it has no ui.jsx,
ui.css, toastctx.js, hashtab.js. Ask for the branch state, do not rediscover.
Design brief: light theme, Navy #0F2747, Teal #0F8B8D, Blue #3B82F6, bg #F5F7FA,
white cards, border #E2E8F0, text #172033/#64748B, ok #16A34A, warn #F59E0B,
err #DC2626. No extra colors, no flashy effects, keep all working logic.
### How to save the owner's chat limit (works well)
- Read the file ONCE with: awk '{print NR": "$0}' F.jsx | fold -w 88
- Then send the whole rewrite in ONE message: numbered blocks of 30 lines or
  fewer, each cat > (first) or cat >> (rest), lines under 90 chars.
- Last block = wc -l, npm run build 2>&1 | tail -2, npm run lint 2>&1 | tail -2.
  Owner sends ONE screenshot. Then a browser test list, then ONE commit paste
  that also prints the next screen (git log -1, wc -l, awk of next file).
- Back up first: cp F.jsx /tmp/F.bak. Restore with cp if the test fails.
- Compare every API field and prop against the old file (a Students bug:
  d.active_term vs d.active_term.id was caught only later).
### UI DONE on ui-redesign (pushed). Build OK, lint 0 errors (16 warnings = baseline)
- 7dd0d26 new app shell (navy sidebar, mobile bar) wired into App.jsx
- a53cc87 hash routing for pages (frontend/src/hashtab.js)
- e93f862 Root.jsx wraps the app in ToastProvider
- cab8f94 Teachers: DataTable, status badge, ConfirmDialog for deactivate,
  Modal for reset password, add teacher, assign table, toasts
- b1e485c + abd4340 Students: add form + total card + toasts (no list yet)
- 7257798 Exams: table, confirm before publish, results table
- Marks.jsx: REWRITTEN (107 lines), build OK. Browser test and commit may be
  pending when this was written: check git log before redoing it.
ui.jsx exports: Button(kind teal|secondary|ghost|danger, size sm, busy), Field,
Input, Select (label,id), Modal(title,onClose,actions), ConfirmDialog(title,text,
confirm,danger,onYes,onNo), ToastProvider, Card(title), Badge(kind ok|err|info|
teal|warn), Alert, EmptyState, Loading, ErrorState(text,onRetry), StatCard,
DataTable(cols{label,key,get,render,sort}, rows, search, empty).
Toast: const toast = useToast() from ./toastctx; toast(text, "ok"|"err").
### UI LEFT (in this order, one commit per screen, test each in the browser)
1 Commit Marks after a TEACHER test: names in dropdown, save shows toast, rows
  become draft, submit asks to confirm. Then F7 extras: paper selector, autosave,
  paste from sheet, bulk absent, rules 0-100 (open question: minimum 1?).
2 Migrate: Approvals, Terms, Setup, Quick, Mine, Deputies, Accounts, Platform,
  Activity, Analytics, Stats, ReportCards, Password. Login last (F9: remove
  fake remember-me/Google/Apple/Sign up; compress login-pic.png 2.2 MB to WebP).
3 Students and Teachers still need a real student list (search, sort, status,
  class) and edit. Read the API fields first, do not guess.
4 F5 admin dashboard (needs attention first, KPI cards). F6 teacher home.
  Teachers see Home + Marks only.
5 F8 Ctrl+K search + bell (needs B12/B13). F10 mobile pass + accessibility
  (focus, labels, contrast, not color alone). F11 offline marks. F12 reports and
  print. F13 vitest.
6 Final audit of EVERY page against the brief: colors, radii, spacing, buttons,
  empty/error states, mobile tables. Fix, do not just list.
7 Merge: open a PR ui-redesign -> main, wait for green CI (npm build, lint,
  229+ backend tests), then merge. Render redeploys main. Never merge a red CI.
### BACKEND LEFT (none changed in this UI part; baseline 229 tests)
B6 SchoolSettings, B7 report cards (show "did not sit"), B8 Student.status +
promotions, B9 CSV import, B10 Subject.definition check, B12 /api/search/,
B13 /api/notifications/ (also notify admin when students are not ranked),
B15 analytics official vs draft, B16 /api/students/<id>/profile/, B17 indexes,
B19 cleanup (dead MAILERS, urls.py imports, "if False" hack, stale docs).
B5 follow-ups: check login JSON has no "refresh"; check expired session goes
to the login screen.
### OPEN OWNER DECISIONS (ask one at a time)
Grading scale per school (CBC EE/ME/AE/BE, 8-4-4, or both), assessment weights,
student/parent portals, PDF method (print vs server), reject a mark of 0.
Theme is settled by the design brief: light navy/teal.
### GOTCHAS
- HANDOFF.md (old) has uncommitted rewrites with stale facts (VITE_API_URL,
  171 tests). Do not commit it. This file is the live handoff.
- Never re-add VITE_API_URL in Render (cookie auth needs the /api rewrite).
- Teachers/parents never see ranks. Keep draft>submitted>approved>locked.
- UI: Marks (7d7003b) and Approvals migrated, browser-tested.
- UI: Terms migrated, browser-tested.
- UI: Setup migrated, browser-tested.
- UI: Quick migrated, browser-tested.
- UI: Mine and Deputies migrated, browser-tested.

### UI STATUS UPDATE (end of chat 2, 5 Oct 2026). READ THIS FIRST.
Branch ui-redesign. Build OK, lint 0 errors (19 warnings, hook deps only).
COMMITTED AND BROWSER-TESTED: Teachers, Students, Exams, Marks, Approvals,
Terms, Setup, Quick, Mine, Deputies.
COMMITTED BUT NOT BROWSER-TESTED (build + lint only): Platform, Accounts,
Activity, Analytics, Stats. FIRST JOB: owner tests these five, fix any bug.
 Platform (superuser): table loads, password hidden, Create needs 4 fields.
 Accounts (superuser): role/status badges, Reset opens modal + toast.
 Activity: names and "x ago". Analytics: teal bar, warning if pending marks.
 Stats: admin 7 cards, teacher 1 card, four text badges.
### STILL TO MIGRATE (old code, untouched)
ReportCards.jsx (16 lines): listAll /api/students/, GET
 /api/report-card/<student>/<d.active_term.id>/ gives student{name,
 admission_number}, term, academic_year, subjects[{subject,average}],
 overall_average, published_results[{exam,class_rank,stream_rank}],
 pending_marks, plus a window.print button. Keep all. Ranks: admin and
 deputies only, check who can open this screen.
Password.jsx (19 lines): POST /api/auth/change-password/ {old_password,
 new_password}, repeat-password match. Re-read the file first.
THEN: Login (F9), shell/Dock/Hero/Intro/Splash/Logo review, Students LIST (read
 API fields first), F5 admin dashboard, F6 teacher home, F7 marks extras, F8-F13,
 final audit of every page + mobile, then PR ui-redesign -> main, merge on green CI.

### PROGRESS 5 Oct 2026 (chat 3, ui-redesign)
- ReportCards.jsx migrated and browser-tested (commit 5d76dab). Ranks stay admin and
  deputy only: the API leaves published_results out for teachers (report_cards.py
  line 68), and the screen guards it with (rc && rc.published_results) || [].
- Password.jsx migrated and browser-tested (Input, Button, Alert, busy state).
- Platform, Accounts, Activity, Analytics, Stats: owner SKIPPED the browser test for
  now. They are still NOT browser-tested. Do it later.
- Old-file backups go to /tmp/X.bak before each rewrite (the routine above).
- NEXT: Login (F9), then shell/Dock/Hero/Intro/Splash/Logo, Students LIST, F5-F13.
- Login.jsx F9 DONE and browser-tested: removed fake remember-me, OR CONTINUE WITH,
  Google, Apple, Sign Up. Kept Forgot password (same rmrow div). Backup was /tmp/LG.bak.
- login.css may still hold unused rules (.soc, .alt, .orc, .su). Check before deleting.
- NEXT: review shell/Dock/Hero/Intro/Splash/Logo, then Students LIST, F5-F13.
