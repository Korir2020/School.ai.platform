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
