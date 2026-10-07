# MARIAN HANDOFF, SESSION 9 (rewritten 6 Oct 2026)
Done items removed (old text is in git history and /tmp/H9.bak).
READ THE BOTTOM SECTION "## NEXT" FIRST. It is newer than the rest.
Update the PROGRESS LOG at the bottom only when the owner says so.

## OWNER RULES (follow exactly)
- Owner works ONLY on a phone in GitHub Codespaces. ONE action per message.
- Pastes of 30 lines or fewer (cat > then cat >>). Give the exact folder.
- Lines under 90 chars. Never paste "read -s".
- Ask for exact output (wc -l, "Ran N tests / OK", screenshot) before trusting.
- Do not trust "no issue". Read screenshots carefully.
- ls before any mv or cat > on an existing file. Back up to /tmp/X.bak first.
- git status --short before every commit. git add ONLY the files you wrote.
- HANDOFF.md (old) has uncommitted edits: never add it to a commit.
- Ignore hosting/paid plans. No real student data yet.
- Ranks/results: school admin + deputies only. Teachers/parents never see ranks.
- Deputy can do everything admin can EXCEPT appoint/remove deputies.
- NEVER BREAK: marks draft > submitted > approved > locked. AI/analytics never
  change official records. Server-side permission checks only.
  Other school = 404, wrong role = 403, anonymous = 401.
- Additive migrations with defaults. Never reset the DB. No rewrite of the app.
- No new libraries unless clearly needed. Theme: light navy/teal (settled).
- Every backend feature: model, migration, serializer, view, URL, permissions,
  tests.
- Tests (from backend/): export DJANGO_DEBUG=True; python manage.py test
  Frontend: cd frontend; npm run build; npm run lint.

## STACK
Django 6.1 + DRF + SimpleJWT (backend/). React 19 + Vite, plain JSX, no router
(hash routing in frontend/src/hashtab.js). Render (practice). Repo root:
/workspaces/School.ai.platform. Branch: main (ui-redesign was merged).

## STATE (6 Oct 2026)
SUPERSEDED, see bottom. (was 254 tests). Frontend build OK, lint 0
errors (22 warnings, hook deps only = baseline). Working tree clean.

## KNOWN FACTS (do not rediscover)
- Roles today: SchoolAdminProfile (is_deputy flag) and TeacherProfile. No
  membership, join-request or invitation model yet. School.code is unique.
- TeacherAssignment = teacher + school + subject + STREAM (stream is required).
- Notifications (api/notifications.py) are computed live, nothing stored.
- There is NO fee, bursar or secretary code anywhere in the repo.
- api/permissions.py: IsSuperAdmin, IsSchoolAdmin, IsTeacher,
  get_user_school_id, is_teacher_only, restrict_for_teacher.
- Auth: refresh token in HttpOnly cookie marian_rt; access token in memory.
  Render rewrite /api/* makes one origin. NEVER re-add VITE_API_URL.
- Mark range is 1-100 (DB constraint). 1 = absent and counts in the overall.
- Login throttle 10/min per IP. Lists 50 per page; use listAll() in api.js.
- Test convention: "from . import tests as base"; never import test classes.
  Test client keeps cookies: self.client.cookies.clear() for "no token".
- A teacher with NO TeacherAssignment sees nothing (tests need Assignment and
  Enrollment).
- Prefix CSS classes mu-. ui.jsx: Button, Input, Select, Modal, ConfirmDialog,
  Card, Badge, Alert, DataTable, StatCard. Toast: useToast() from ./toastctx.

## PROJECT A: PUBLIC LANDING + SECURE STAFF ONBOARDING (brief of 6 Oct 2026)
Owner keeps the full 38-section brief; ask them to paste it again if needed.
Do not rebuild Marian. Preserve all existing users and logins.
FLOW: Landing (public) > Get Started > Request to join (School Code only
identifies the school) > admin/deputy approves > Marian makes a one-time
invitation code > admin shares it > staff enters it and joins > admin gets
"New staff member" notification with Assign > admin assigns responsibilities.
SECURITY: School Code is NOT authorization. Invitation code: random, unique,
tied to school + request + user, expires, single-use, never the School Code.
Never trust role/school/subjects/codes from the frontend. School isolation.
Only that school's admin/deputy approves, rejects, generates codes, assigns.
DECISIONS MADE (6 Oct 2026):
- Roles: Teacher, Bursar, Secretary (admin/deputy stay). More roles later.
- Bursar and Secretary: NO subject list. Activities assigned AUTOMATICALLY by
  role. Their activity lists stay EMPTY for now (no such features exist yet).
- Teacher: after joining, admin/deputy gets a notification with Assign and
  picks subjects from the school's list, MAXIMUM 4 (frontend AND backend).
  Editable later without deleting the teacher.

### Project A steps (A0-A2 DONE, see bottom)
A0 Answer the open question. Read teacher serializers/views and login first.
A1 Models + migration: JoinRequest (user, school, role, status, audit) and
   InvitationCode (random, expiry, used_at, school, request).
A2 API: request-join; list/approve/reject (that school's admin/deputy only);
   code generation; complete-join (validate every rule, atomic, rate limited).
A3 Stored notifications (new model) merged into /api/notifications/. Keep the
   two computed kinds. Add mark-as-read.
A4 Assignment API: teacher subjects max 4 (server side), edit, role auto-assign.
A5 Tests for A1-A4 incl. other school 404, wrong role 403, anonymous 401.
A6 Frontend: public landing (add a public screen before Login), Get Started,
   pending/approved/complete screens, Sign In. Mobile first, light theme.
A7 Frontend: admin Staff Management (pending, recent, assign) + bell.
A8 Browser pass on the phone, then update this handoff.
LANDING PAGE: show only real features (students, teachers, exams, analytics,
report cards, staff). Fees do not exist: do not advertise them. No real data.

## OTHER PENDING WORK (after Project A, in this order)
1 Owner browser tests (one slow pass, do not ask): Marks (F7 parts 1-5),
  ReportCards did-not-sit, Platform, Accounts, Activity, Analytics, Stats.
2 F8 Ctrl+K search + bell (B12 search and B13 notifications APIs exist).
3 Frontend for B15: term-summary "unofficial" field. Read-only display.
4 F10 mobile + accessibility, compress login-pic.png to WebP, check login.css.
5 F11 offline marks. F12 print/reports. F13 vitest.
6 Backend: B6 SchoolSettings, B7 report card grades/comments, B8 promotions,
  B9 CSV import, B10 Subject.definition check, B16 student profile,
  B17 indexes, B19 cleanup (dead MAILERS, urls.py, "if False", stale docs).
7 E0: teachers may over-read dashboard, analytics, progress, early warning,
  exam results, mine. Check and fix.
8 Final audit of every page and mobile.
9 ANALYTICS ENGINE (owner keeps the 30-section spec), only after the UI:
  E1 central api/engine/, E2 max_mark + statuses, E3 aggregation + rounding,
  E4 grading schemes, E5 report cards, E6 analytics, E7 UI, E8 CBC,
  E9 KCSE, E10 Cambridge. Settle first: absent vs zero, parent views, grading.
## OPEN OWNER DECISIONS (one at a time)
Grading scale per school, assessment weights, portals, PDF method.
## PROGRESS LOG
- 6 Oct 2026: B15 done (b8b5d62). Handoff rewritten.
- 6 Oct 2026: A3 done (380664a), A4 done (b8d363d), A6 code written.

## PROJECT A: DECISION + A0 FINDINGS (6 Oct 2026)
DECIDED: admin picks up to 4 DISTINCT subjects. Marian then shows each chosen
subject separately and the admin picks the exact classes/streams the teacher
teaches for that subject. The limit counts subjects, not streams.
A0 findings (api/admin_create.py): _create(request, serializer_class, owners,
inject_school, check) is the safe creator: admin-only (403), copies request
data, forces school from the server, rejects records of another school, then
runs check(v). _assignment_check blocks duplicates. admin_edit.py edits.
Plan: reuse _create; add a check that counts the teacher's distinct subjects
plus the new one (max 4); never trust school/role from the frontend.

## STATE END OF CHAT (6 Oct 2026). Backend 268 tests OK. Frontend unchanged.
Zip of the repo may be older than GitHub main: ask for git log -3 first.
DONE (committed, pushed):
- B15 unofficial marks in term summary: api/unofficial.py. UI not showing it yet.
- A0 audit. A1 models + migration 0027 in schools/models.py: JoinRequest,
  InvitationCode, StaffProfile. One open request per user (DB constraint).
- A2 join API (api/join_codes.py, join_public.py, join_admin.py,
  join_complete.py, join_throttle.py; urls; throttle rates in settings):
  POST /api/join/register/ (public: username, password, first/last name,
    role teacher|bursar|secretary, school_code). Makes user + pending request.
  GET /api/join/my-request/ (status + message). POST /api/join/complete/ {code}.
  GET /api/join-requests/?status= (admin/deputy, own school only).
  POST /api/join-requests/<id>/approve/ and /reject/ (404 other school, 403
    teacher, 401 anonymous, 409 wrong state). Approving an already approved
    request reissues a NEW code (use it when a code expired).
- Code rules: MARIAN-XXXXXX (no 0/O/1/I), 7 days, single use, tied to the
  request + user. Complete-join checks the caller's OWN approved request.
  Creates TeacherProfile (teacher) or StaffProfile (bursar/secretary).
- Audit actions in MarkAuditLog: join_requested, join_approved, join_rejected,
  join_completed. Tests: api/test_join_flow.py (14).
- Registration uses username + password (no email, no phone collected yet).

## NEXT (OLD, superseded by the LAST section at the bottom)
A3 Stored notifications. New Notification model (school, recipient user or
  admin/deputy of school, kind, message, read_at, link to JoinRequest). Create
  on: join_requested (admins: "New Staff Request", Approve/Reject),
  join_completed (admins: "New staff member", Assign), approved/rejected (the
  staff member). Merge into /api/notifications/ (today computed, admins only,
  teachers get 403: staff must read their OWN). Keep the 2 computed kinds. Add
  mark-as-read. Hook the creation into join_public.py, join_admin.py and
  join_complete.py. Tests incl. other school never sees them.
A4 Assignment API: admin picks up to 4 DISTINCT subjects, then per-subject
  streams (reuse admin_create._create + a check; editable later). Bursar and
  Secretary: auto role, activities EMPTY for now. ALSO: /api/auth/me/ returns
  role "none" for StaffProfile users; get_user_school_id in permissions.py
  ignores StaffProfile. Fix both (school isolation) with tests.
A6 Frontend: public landing, Get Started, request status, complete-join.
A7 Frontend: admin Staff Management (pending, approve/reject, code, assign),
  bell using stored notifications. A8 phone browser pass.
Then: OTHER PENDING WORK list above. Never advertise fees (do not exist).

## STATE END OF CHAT (6 Oct 2026, part 2). READ THIS SECTION FIRST.
Backend 280 tests OK. Frontend build OK, lint 22 warnings 0 errors (baseline).
DONE (committed and pushed unless marked):
- A3 stored notifications (380664a). Model Notification (migration 0028), one row
  per recipient. api/notify.py: notify_admins (every admin/deputy of THAT school),
  notify_user, stored_items. api/notify_read.py: POST /api/notifications/<id>/read/
  and /api/notifications/read-all/ (own rows only, others 404).
  GET /api/notifications/ = computed items (admins only) + own stored items +
  "unread" count. Teachers/staff now get 200 with only their own (old 403 test
  changed). Created on join_requested (admins), join_completed (admins),
  approve/reject (the staff member, no code in the text).
  Tests: api/test_notifications_stored.py (6).
- A4 (b8d363d). Max 4 DISTINCT subjects per teacher on POST /api/teacher-assignments/
  (more streams of one subject are fine; deleting frees a slot; assignments have no
  PATCH, so edit = delete + add). /api/auth/me/ returns role bursar or secretary
  for StaffProfile users. DECISION: get_user_school_id was NOT changed on purpose,
  staff get 403 on every data endpoint (else they could read all school data).
  Tests: api/test_staff_assign.py (6). A5 is covered by these tests.
- A6 frontend CODE written (committed), build and lint OK, NOT YET TESTED IN A BROWSER:
  Landing.jsx + landing.css (story showcase, 10 chapters: Learning, Academic
  Excellence, Assessment, Student Development, Talent & Sports, Leadership,
  Character, Innovation, Achievement, Community; scroll reveal; pinned Get Started
  and Sign In bar), Join.jsx (request form, posts /api/join/register/),
  JoinStatus.jsx (pending, enter invitation code, joined, rejected; also shown when
  me.role is none, bursar or secretary), pub.css. App.jsx flow: Intro > Landing >
  Join or Login; logout returns to Landing.

## NEXT (do in this order, one commit each)
1 A6 browser pass on the phone. vite.config.js proxies /api to the RENDER practice
  site: do NOT register test users there. Use a LOCAL backend: runserver in backend/
  plus an untracked frontend/vite.local.config.js (proxy target http://localhost:8000),
  run npx vite --config vite.local.config.js. Never commit that file.
  Check: hero, chapter reveal, pinned bar, Get Started form + Back, Sign In,
  register, pending screen, admin approves, code entry, joined screen.
2 A7 admin Staff Management: pending list, Approve/Reject, show the code, Assign
  teacher subjects (max 4, then streams), bell with stored notifications and
  mark-as-read. join_completed notification only has join_request_id: Assign may
  need the teacher id exposed by the API.
3 A8 phone pass, then update this handoff. Landing: add real school photos later.
4 Then the OTHER PENDING WORK list above.

## PROJECT B: SCHOOL ADMIN ONBOARDING (planned 7 Oct 2026, NOTHING BUILT)
Git then: 5d7bcb1 B15 UI, 7f28aa6 F8 search, a0cdf19 A7 bell. Tree clean
except untracked frontend/vite.local.config.js (never commit it).
Owner has the full 22-section brief: ask them to paste it again.
GOAL: new school registers, Marian superadmin approves, applicant becomes the
first School Admin, then a setup wizard. Project A staff flow stays untouched.
School Code never gives admin rights.
DECISIONS: new model SchoolRegistration (NOT School; no School or User exists
before approval). Password hashed only. States: PENDING_VERIFICATION, VERIFIED,
PENDING_APPROVAL, NEEDS_INFORMATION, APPROVED, REJECTED.
Approval = one transaction.atomic: recheck state and code free, create School,
User, SchoolAdminProfile, mark APPROVED, audit. Roll back on any failure.
No OTP/SMS in repo: hashed code state, pluggable delivery, DEBUG prints to
console only, never fake sending. Add School setup-completed field (migration).
Backend decides setup completion. No router: use hash screens (hashtab.js).
No vitest yet (F13): ask owner before adding any library.
ORDER (one commit each): B1 model, submit, status, throttle, audit, tests.
B2 verification. B3 superadmin list/review/approve/reject/need-info + tests.
B4 setup flag + isolation tests. B5 public screens. B6 superadmin screens.
B7 setup wizard (profile, year, terms, classes, subjects, staff).
NOTE: /api/dashboard/ is OK for staff (403 via _scope). Real item is E0.
Reuse: join_throttle, notify_user, MarkAuditLog, admin_create._create.

## B1 STATE (7 Oct 2026) READ THIS FIRST FOR PROJECT B
Claude wrote B1 in a sandbox with NO Django: code is only syntax checked.
NOTHING IS TESTED. Files came as B1_school_registration.zip (8 files):
schools/models.py, migrations/0029_school_registration.py,
api/school_registration.py, otp_delivery.py, join_throttle.py,
test_school_registration.py, config/settings.py, config/urls.py.
If the zip was never unzipped, rebuild from this section.
B1 design: model SchoolRegistration (hashed password_hash, otp_* fields,
info_request_message, info_response, internal_notes, reference MSR-XXXXXXXX,
OneToOne school). Constraints: unique open code and lower(username).
School gained school_type, county, sub_county, setup_completed_at (old
schools backfilled as set up). School address maps to School.location.
MarkAuditLog.school now nullable (registration events have no school).
Audit action max length is 30 chars: use short names (school_reg_submitted).
POST /api/school-registration/ (public, throttled 3/hour) creates only a
registration. POST /api/school-registration/status/ {reference, username}
returns applicant-safe data only (POST so nothing sits in URLs).
otp_delivery.deliver_otp: DEBUG prints to console, production returns False.
No terms/privacy feature exists (Terms.jsx is academic terms): skipped.
## PROJECT B TODO (one commit each, tests first, nothing claimed untested)
B1b: unzip in repo root; from backend/: python manage.py makemigrations
 --check (want "No changes"); export DJANGO_DEBUG=True; python manage.py
 test api.test_school_registration; then full test run; commit by name.
B2 verify: POST /api/school-registration/verify/ {reference,username,code}.
 Generate OTP at submit, store make_password hash, expire 10 min, max 5
 attempts, resend cap and cooldown (otp_send_count, otp_sent_at). Success:
 pending_verification > verified > pending_approval in one atomic block, audit
 "school_admin_verified". Never log codes. OPEN OWNER DECISION: no SMS
 provider, so how do real applicants verify in production?
B3 superadmin (IsSuperAdmin only): list, retrieve, approve, reject,
 request-info, plus applicant POST /info/ (needs_information >
 pending_approval). Approve = transaction.atomic + select_for_update:
 recheck state and code free, create School (copy fields), create User with
 user.password = reg.password_hash (never create_user with the hash), create
 SchoolAdminProfile (is_deputy False), mark approved, audit. Reject and
 request-info need a reason. Never serialize internal_notes to applicants.
 Tests: rollback via mock, teacher/bursar/secretary/anonymous blocked.
B4 setup: backend computes complete = profile filled + active year + 1 term
 + 1 stream + 1 subject. GET /api/setup/ status, POST /api/setup/complete/
 sets setup_completed_at + audit. /api/auth/me/ returns setup_complete.
 Admin edits OWN school profile via a new limited endpoint (School is not
 editable today); keep the code read-only. Isolation tests.
B5 public screens (hash routing, no router): landing "Register Your School",
 form, verify, status. B6 superadmin list + review screens.
B7 wizard: profile, year, terms, classes, subjects, staff (reuse Terms.jsx,
 Setup.jsx, Staff.jsx, admin_create._create). Mobile first, mu- classes.
E0: add a test that /api/dashboard/ never gives staff teacher data.
LATER: school suspend (no field yet), frontend tests (ask before any new
 library), final build and lint, update CHANGELOG.
