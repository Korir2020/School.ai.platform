# Marian handoff (2 Oct 2026). Read this first, then AI_CONTEXT.md.
## How to help the owner
Works only on a phone in GitHub Codespaces. Give ONE action at a time, pastes of 30 lines or fewer, with the exact terminal location. Tap inside the terminal before pasting. Never put "read" prompts inside a long paste. Ask for the exact output lines before trusting "success". Full test run takes about 4-5 minutes.
## Repo
Django REST backend in backend/. requirements.txt is a full freeze; requirements-prod.txt is what Render installs. Older history is in AI_CONTEXT.md.
## DONE (tested: 139 tests pass on sqlite and on PostgreSQL)
- Pagination on list endpoints: {count,next,previous,results}, 50 per page, ?page_size= up to 200 (api/pagination.py)
- JWT blacklist and POST /api/auth/logout/ (api/auth_logout.py)
- Env-driven settings: PostgreSQL (DB_*), CORS (DJANGO_CORS_ORIGINS), CSRF origins; whitenoise and gunicorn added
- LIVE on Render free plan: https://school-ai-platform.onrender.com ; /api/health/ ok; /admin/ works; login, list, logout and blacklist verified live
- API docs: drf-spectacular, /api/docs/ and /api/schema/ admin-only (anonymous gets 401), api/test_api_docs.py, 142 tests pass on sqlite, live on Render
- Uptime monitor: UptimeRobot free, 5-minute checks on /api/health/. Check their terms before real schools (free plan may be non-commercial)
## Render setup (values only in Render, never in git)
Build: pip install -r requirements-prod.txt && cd backend && python manage.py collectstatic --noinput && python manage.py migrate && python manage.py loaddata schools/fixtures/catalogues.json && python manage.py extend_cambridge_catalogue && (python manage.py createsuperuser --noinput || true)
Start: cd backend && gunicorn config.wsgi. Root directory blank. Region Frankfurt. Env vars: DJANGO_SECRET_KEY, DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS, DJANGO_NUM_PROXIES, DB_NAME/USER/PASSWORD/HOST/PORT, DJANGO_SUPERUSER_USERNAME/EMAIL/PASSWORD. Render Shell is paid, so seeding is in the build command.
## Gotchas learned
Free Render Postgres expires after about 30 days: NO real student data on the free tier. Local test DB: sudo service postgresql start, then export DB_NAME=marian DB_USER=marian DB_PASSWORD=devpass DB_HOST=localhost; create the DB user with: echo "SQL" | sudo su postgres -c psql. On Render, tap Edit before Add Environment Variable appears. Stuck terminal: tap the trash icon and open a new one.

## SESSION 5 STATE (authoritative; old NOT DONE list removed)
Trust the DONE items; do not re-verify them. Start at NEXT STEPS.
Before committing: git status --short; add only files you wrote (a stray editor space once showed as M; undo with git checkout -- file).
DONE and pushed (tested):
- GET /api/analytics/early-warning/ (admin): students whose latest average fell 10+ points since the previous published exam, or is below 40. {count, results:[{student_id,name,admission_number,latest_average,reasons[]}]}. api/early_warning.py, test_early_warning.py (4 tests)
- GET /api/students/<id>/progress/ (admin): trend (improving/steady/declining/not_enough_data), change, flags (sharp_drop, decline_streak), biggest_subject_drops, from published ExamResult history. api/progress.py (logic), progress_api.py, test_progress.py (5 tests)
Both are read-only and explainable; they never change records.
## NEXT STEPS (in order)
1. Owner decision: may teachers or parents see ranks/results? Today admins only.
2. Optional backend: class-wide subject trend endpoint for charts; verify IGCSE subject list against the official Cambridge list.
3. FRONTEND: new folder frontend/ (React + Vite, installable PWA, works on low-end Android). Host as a Render static site, then set DJANGO_CORS_ORIGINS to its URL on the backend service.
   Screen order: login (POST /api/auth/login/, refresh /api/auth/refresh/, access token 15 min, refresh 7 days, logout POST /api/auth/logout/), role dashboard (GET /api/dashboard/, role from GET /api/auth/me/), teacher mark entry, admin approvals, exams + publish + results, students/setup, report cards, analytics + early-warning + progress. Offline sync and extra languages last.
   Lists return {count,next,previous,results}, 50 per page, ?page_size= up to 200.
4. Before real schools: paid Render plan, new admin password, backups. No real student data on the free tier.
Last full test run 2026-10-02: OK 

## Frontend status (Oct 2026)
- Live site: https://marian-app-1mzf.onrender.com (Render static site: root frontend, build "npm install && npm run build", publish dist, env VITE_API_URL=https://school-ai-platform.onrender.com). Backend env DJANGO_CORS_ORIGINS is set to that URL.
- Dev: cd frontend && npm run dev (vite.config.js proxies /api to Render; frontend/.env has VITE_API_URL empty).
- Built: splash, branded login, tab layout, installable PWA (manifest + icons, no offline mode).
- Teacher tabs: Home, Marks. Admin tabs: Home, Approve, Exams, Reports (print), Analytics, People (add students, add teachers, assign), Setup (streams, subjects).
- Backend added: /api/teachers/ (GET list, POST create), all schools models registered in Django admin.
- Practice data on Render: Marian test school, admin Joscheryoto, teachers teacher1 and teacher2.

## Pending
- Owner to review splash and layout on phone and request fixes.
- No in-app screens yet for: creating schools or the first admin, academic years and terms (Django admin only).
- No password change/reset; no parent or student screens.
- Open decision: may teachers or parents see ranks and results (admin only today).
- Logo in the app is a redrawn SVG and simplified PNG icons; swap in the real logo files.
- Before real schools: paid Render plan, strong admin password, backups. No real student data on the free tier.
- Early warning screen skipped by owner.

## How marks, ranks and analytics work (from the code)
- Exam subject score = sum of (paper marks x paper weight / 100). No paper setup means one paper at 100%. Paper weights must total 100 or publish is refused.
- Exam overall average = plain average of a student's subject scores (all subjects equal), 2 decimals.
- Rank = 1 + number of students with a strictly higher average, so ties share a rank (1, 1, 3). Class rank covers the class level, stream rank covers the stream.
- Ranks are fixed at publish as a snapshot. Publish is refused unless every paper is approved or locked.
- Report card: subject average = mean of that subject's approved or locked marks across opener, mid and end. Overall = mean of subject averages. Unapproved marks are excluded and shown as pending.
- Analytics term summary: per subject average, highest, lowest and entry count from approved or locked marks only, plus the pending count.
- Open rule question: report cards average all assessments equally. If the school wants weights for opener, mid and end, change the backend (api/report_cards.py).

## Session 6 (3 Oct 2026)
- DONE, tested and live: Setup tab now has Academic years and terms (frontend/src/Terms.jsx): add year, add term, turn term on or off.
- DONE, tested and live: POST /api/auth/change-password/ (api/auth_password.py, 5 tests in test_password.py, all pass) and a Change password box at the bottom of Home for every role (frontend/src/Password.jsx). Checked live with teacher1.
- NOTE: Term 3 2026 starts 11 Oct but the 2026 year starts 21 Oct (entered in Django admin, which does not check). Editing that term's dates in the app will be refused until the dates agree.
- STILL OPEN: owner decision on teacher/parent view of ranks and results; parent and student screens; creating schools and first admin in-app; real logo files; paid Render plan, strong admin password and backups before real schools.

## Session 6, part 2 (3 Oct 2026)
- DONE, tested and live: Edit dates for academic years and terms (Terms.jsx). The school sets its own dates. Term dates must stay inside the year. Practice data fixed (year 2026 now starts 1 Sep).
- DONE, tested and live: DEPUTY role. A deputy is a SchoolAdminProfile with is_deputy=True (migration 0025), so every existing admin check applies to deputies unchanged: approvals, exams, ranks, report cards, analytics, setup, adding and assigning teachers.
- Only a non-deputy school administrator can use /api/deputies/ (GET, POST) and /api/deputies/<id>/ (DELETE). Deputies get 403. Removing a deputy deletes the profile and deactivates the login, so it cannot sign in again. Deputies get a separate new login.
- /api/auth/me/ now returns is_deputy. The Deputies box (Deputies.jsx) shows in the People tab for the administrator only.
- DECIDED by owner: ranks and results are seen by the school administrator and the deputies he appoints. Teachers and parents do not see ranks or results.
- Full test run: 171 tests OK (api/test_deputies.py has 9, api/test_password.py has 5).
- NEXT: item 3, fixes to the look of the app (owner to name the first thing that looks wrong). Still open: parent and student screens, creating schools and the first admin in-app, real logo files, paid Render plan, strong admin password and backups before real schools.
## Session 7 (4 Oct 2026): login redesign
DONE (checked in a browser preview; owner likes the design):
- New login: transparent black/gold glass box, "Welcome Back", username + password with eye button, yellow Sign In. Files: frontend/src/Login.jsx, login.css, backgrounds.css. App.jsx now imports Login from ./Login; the old function was renamed OldLogin (unused, safe to delete with the Scene import).
- Two corners (top-left, bottom-right) look folded like dog-ears.
- Success animation just pasted, NOT yet confirmed on the phone: corners fold inward, gold creases cover the box, MARIAN logo seal, box zooms into the dashboard (.shell fades in).
- Left out on purpose (no backend): Google/Apple login, Sign Up, Remember me, password reset ("Forgot password?" says ask the administrator).
- Why old background edits never worked: the Scene.jsx SVG covers CSS backgrounds, and body in app.css paints the app blue.

REMAINING (in order):
1. Save Login.jsx and login.css, then confirm the new login animation on the phone.
2. Login background: still a placeholder gold gradient (--bg-login in backgrounds.css). Owner uploaded pictures to frontend/src/assets. Need exact file names, then use url(./assets/NAME).
3. Picture inside the login box (student at the door, top banner replacing the logo row). CSS class .lgpic already exists. Import the picture from assets and add <img className="lgpic"> in Login.jsx.
4. Welcome background (Welcome.jsx, Scene.jsx, welcome.css). Owner has uncommitted experiments: Universe.jsx, universe.css, Welcome.jsx.backup.
5. Background inside the app tabs (body gradient in app.css). Move it to backgrounds.css. A light background also needs the card and text colors changed.
6. Small fixes: splash tagline overlaps MARIAN; delete unused App.css (capital A, Vite leftover).
7. git add, commit and push so Render rebuilds the live site.
## SESSION 8 (4 Oct 2026) READ THIS FIRST. Older NEXT and REMAINING lists are done or stale.
OWNER RULES: phone only, Codespaces. ONE action per message, pastes <=30 lines (cat > then cat >>), exact folder, ask for exact output. Owner wants a batch of changes finished, then tests everything and sends a numbered fix list (screen + problem). Before any mv or cat > on an existing name, run ls first (a mv once wiped Login.jsx).
DONE and pushed: gold glass login (Login.jsx, login.css, backgrounds.css): Welcome Back box, username then password, Sign In after 4 chars, password spin while checking, shake on wrong password, success fold+seal+zoom (slowed). Logo.jsx: book blue, chart gold/black. Black and gold theme: app.css, Analytics.jsx, index.css, Scene.jsx. Blue kept only as accent (active tab, Log out, stat top line).
DONE this session: Inter font (npm install @fontsource-variable/inter, import is line 1 of frontend/src/main.jsx) and a "Marian theme v2" block at the end of app.css (tokens, blue buttons, gold numbers, subtle gold-dark borders). Owner has NOT reviewed v2 on the phone yet.
DASHBOARD REDESIGN (owner prompt, agreed). Keep the Marian palette: near-black, gold for numbers and brand, electric blue for nav, buttons, active states. Premium instrument-panel look, mobile first (360-430px), radius 14-18px, thin low-opacity borders, no heavy glow, no fake data, nothing removed. Decisions: blue in-app buttons, gold numbers; bottom dock with 5 items (Home, Approve, Exams, Reports, Analytics) plus a More item that opens Students, Teachers, Setup; Inter font. The owner has the full prompt text and can paste it again.
BUILD ORDER (one commit per step, owner tests at the end):
2. Header (logo + MARIAN, user, outlined Log out) and compact welcome with an "active term" dot (frontend/src/App.jsx Home and Dash).
3. Stat cards: small uppercase label, controlled number, short description, blue top edge. One MARKS OVERVIEW module (Draft, Submitted, Approved, Locked) with a thin meter from real counts in GET /api/dashboard/.
4. Quick Actions row (Approve Marks, Exams, Reports, Students, Analytics) that switch tabs.
5. Recent activity from GET /api/audit-logs/ (admin, max 200 rows).
6. Bottom dock with icons plus More.
7. Split the People tab into Students and Teachers tabs (Deputies box goes under Teachers, non-deputy admin only). Teachers get a simpler Home.
