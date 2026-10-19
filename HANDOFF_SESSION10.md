# HANDOFF SESSION 10 (newest; older handoffs are stale)
STATE: full suite green (356 + new setup tests). B1 registration, B3 superadmin
review, B4 setup backend are BUILT. Teacher transfers built. Admin safety built.
NEXT, in order:
1. B2 applicant verification: no SMS provider, so use EMAIL OTP (decision pending).
   POST /api/school-registration/verify/, 10 min expiry, max 5 attempts, hashed code,
   never log codes, audit "school_admin_verified".
2. B5/B6/B7 frontend: setup wizard UI (reuse Setup.jsx), register-your-school
   screens, superadmin review screens. Use GET /api/setup/ and POST /api/setup/complete/.
3. Fix JWT SIGNING_KEY: it is 31 bytes, must be 32+; set via environment variable.
4. staticfiles/ dir warning: fix before deployment.
5. Later: school suspend, financial workflows, analytics + AI features, backups.
GIT: repo https://github.com/Korir2020/Marian (private). Push using `gh auth login`
(browser device login). Never paste tokens into chats.
RULES: inspect before editing, tests first, run full suite, commit by name.

## UPDATE 2026-10-16 (branch onboarding-ui, NOT pushed yet)
DONE (build passes, 383 backend tests pass):
- SchoolStatus.jsx: applicant "Check my application" screen (Landing button, App.jsx route, uses POST /api/school-registration/status/).
- RegistrationReview.jsx: status filter and email-verified badge.
- Backend GET/PATCH /api/school/profile/ (api/profile_views.py, 10 tests in api/test_school_profile.py). Non-deputy school admin edits own school only. Reason: approval never filled location or county, so setup checklist "profile" could never complete.
- SetupWizard.jsx: shown at top of the school admin Setup tab. Checklist, profile form, Finish setup (/api/setup/complete/).
- Label "Senior / Secondary" (stored value stays "secondary").
NOT DONE: browser check of the new screens, auto-open wizard on first login, "resend code" (needs a backend endpoint), needs_information status.
OPEN: DJANGO_EMAIL_* and DJANGO_FRONTEND_URL on Render (registration returns 503 without SMTP); replace DJANGO_SECRET_KEY; check Marian-app repo and branch.
DEPLOY: Render deploys from original main. Backup: ~/marian-backup-2026-10-15.dump (keep it).

## UPDATE 2 (same day, branch onboarding-ui)
DONE since the note above (390 tests pass, build passes):
- Auto-open: a non-deputy school admin with setup_complete false lands on the Setup tab when the URL has no tab (App.jsx).
- Resend code: POST /api/school-registration/resend/ (api/resend_views.py, 7 tests). 60 s cooldown, max 5 sends in total, reuses SchoolRegStatusThrottle, audit "school_reg_resent", 503 without email. Button with countdown in SchoolRegistration.jsx.
STILL NOT DONE: needs_information status (admin request-info action, applicant reply path); browser check of all new screens; SMTP (DJANGO_EMAIL_*, DJANGO_FRONTEND_URL) so registration and resend work live; replace DJANGO_SECRET_KEY; check Marian-app repo and branch.

## UPDATE 3 (end of session, pushed to original main)
LIVE: onboarding UI (status screen, review filter and badge, /api/school/profile/, setup wizard, auto-open wizard, resend code) plus the landing button wrap fix. 390 backend tests pass, build passes.
NEXT SESSION, in order:
1. Browser check on the live site: Landing buttons (two rows, scroll to the bottom), school admin Setup tab wizard, superadmin Registrations Email badge and filter.
2. SMTP on Render: DJANGO_EMAIL_* and DJANGO_FRONTEND_URL (set in Render, never paste values in chat). Without them registration and resend return 503. Then test a real registration.
3. Replace DJANGO_SECRET_KEY (it appeared in earlier screenshots). Do it before real schools use the platform.
4. Check Marian-app (static site) repo, branch, root directory and build command in Render.
5. needs_information: add an admin "request_info" action with a required message (model field info_request_message already exists, no migration). First read how rejected registrations are handled to design the applicant resubmit path.
6. Check marian-db creation date (free Postgres expires about 30 days after creation, no Render backups). Keep ~/marian-backup-2026-10-15.dump.

## UPDATE 2026-10-16 (branch ui-pro, not merged, not browser-tested)
DONE on ui-pro (build passes each step):
- kit.jsx/kit.css: Dialog, ConfirmDialog, Tabs, Badge, EmptyState, Skeleton
- Charts.jsx: SVG trend and distribution, used in Analytics.jsx
- Exams.jsx results: class/stream scope switch, admission no, "No rank"
- AuditLog.jsx: new Audit tab (school admin and superadmin), uses /api/audit-logs/ (mark changes only)
- Shell: breadcrumb and "Active term" line (term prop from App.jsx)
- Platform.jsx: platform totals, school profile dialog
- StudentCenter.jsx: tabbed sections
- Marks.jsx: inline "Use 1 to 100" message
- Analytics insights card relabelled "Automated suggestions" (rule-based, not AI)
Backups of patched files were in /tmp (lost on Cloud Shell reset); git history is the rollback.

NEXT, in order:
1. Browser-test every screen above, as superadmin, school admin, teacher, parent. Fix before merging.
2. Housekeeping: rotate DJANGO_SECRET_KEY, fix 31-byte JWT signing key, SMTP on Render.
3. Frontend: teacher assignment (max 4 subjects, classes/streams per subject), notification center (categories, priority, preferences), parent portal polish, logo options, phone/accessibility pass, unauthorized and session-expired screens.
4. Backend with tests (do not invent endpoints): security center, school suspend and billing, platform health, fuller audit log.
5. Merge ui-pro into main only after step 1, then deploy.
RULES: inspect before editing, patch scripts assert one match, tests first, commit by name.

## 2026-10-17 UPDATE: bright theme, dark mode, new login (branch pro-release)

Done and pushed (frontend only, no backend changes):
- src/styles/marian-theme.css: --m-* colour tokens (brand navy #0B2F66, blue #0A86F0, green #3DB54A, brighter tints), Light / Auto / Dark via data-theme. src/theme.js and src/ThemeToggle.jsx (switch is in Shell.jsx header only). main.jsx imports the theme and calls initTheme().
- Old --mu-* (ui.css) and --txt/--line (light.css, app.css) variables now point at --m-* tokens. Hard-coded white, gold (#facc15) and old dark backgrounds replaced in shell, ui, kit, landing, pub, login, intro, index, app css. Gradients and blur removed from app.css and landing.css.
- src/Login.jsx rewritten: split layout, 16px text, 48px targets, states for loading, disabled, error, locked (60s after "Too many attempts"), suspended (marian:suspended event or error text) and success. Exact suspended text: "This school's account is suspended. Contact Marian support." Styles in src/login-pro.css. Old login.css kept because PasswordRecovery.jsx still uses it.

NOT verified: nothing has been seen rendered. Builds pass, but nobody has checked Light or Dark in the browser yet.

NEXT:
1. Run npm run dev, check Dark mode on: landing, login (phone width), dashboard, a table page, public pages, password recovery. Fix any white boxes, unreadable text or leftover gold.
2. Add ThemeToggle to the landing page and login page (it is only in the signed-in shell).
3. Remaining fixed colours: login.css and intro.css animation rules (logo animation, now unused by Login.jsx), index.css splash glow, kit.css skeleton shimmer.
4. Swap in the owner's logo when supplied (Logo.jsx).
5. Still to design from the brief: registration form, registration-status page, admin dashboard polish (cards, charts, tables), mobile bottom navigation check.

## 2026-10-17 LATE UPDATE
- Fixed: landing hero background was wrongly set to the card colour (white text on white). Now var(--m-side) navy; eyebrow line #7CC4FF.
- Added: ThemeToggle on the login page (still missing on the landing page).
- Render serves a different branch from pro-release (origin has release-for-render, main, ui-pro, ui-redesign). pro-release is NOT merged anywhere yet. To deploy: confirm which branch Render builds, then merge pro-release into it.
- Still unverified in a browser: Light and Dark on all screens. Landing logo wordmark is navy (disappears on dark surfaces) - owner will supply the final logo.
