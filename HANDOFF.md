# Marian handoff. Read this first, then AI_CONTEXT.md (reference only, no logs).
## How to help the owner
Phone only, GitHub Codespaces. ONE action per message, pastes of 30 lines or fewer (cat > then cat >>), exact terminal folder, ask for the exact output before trusting success. Run ls before mv or cat > on an existing name. git status --short before every commit; add only files you wrote.
The owner works in batches: finishes a set of changes, tests on the phone, then sends a numbered fix list (screen + problem).
Backend tests: python manage.py test (about 5 min, expect 171 OK). DJANGO_DEBUG now defaults to False, so run export DJANGO_DEBUG=True in Codespaces first.
Never reuse generic CSS class names across css files (login icons once clashed with the intro cards).
## Live
Backend https://school-ai-platform.onrender.com. App https://marian-app-1mzf.onrender.com (static site: root frontend, build npm install && npm run build, publish dist, VITE_API_URL = backend URL; backend DJANGO_CORS_ORIGINS = app URL). Dev: cd frontend && npm run dev.
Practice data: Marian test school, admin Joscheryoto, teachers teacher1 and teacher2.
## Render backend setup (values only in Render, never in git)
Build: pip install -r requirements-prod.txt && cd backend && python manage.py collectstatic --noinput && python manage.py migrate && python manage.py loaddata schools/fixtures/catalogues.json && python manage.py extend_cambridge_catalogue && (python manage.py createsuperuser --noinput || true)
Start: cd backend && gunicorn config.wsgi. Root directory blank. Region Frankfurt. Env vars: DJANGO_SECRET_KEY, DJANGO_DEBUG=False, DJANGO_ALLOWED_HOSTS, DJANGO_NUM_PROXIES=1, DB_NAME/USER/PASSWORD/HOST/PORT, DJANGO_SUPERUSER_USERNAME/EMAIL/PASSWORD, DJANGO_CORS_ORIGINS. Render Shell is paid, so seeding is in the build command.
## Gotchas
Free Render Postgres expires about 30 days after creation, then 14 days grace, then it is deleted. Web sleeps after 15 min idle. NO real student data on the free tier.
On Render, tap Edit before Add Environment Variable appears. Stuck terminal: tap the trash icon and open a new one. A cut-off paste shows ">" at the prompt: close that terminal and open a new one.
Local PostgreSQL test DB: sudo service postgresql start, then export DB_NAME=marian DB_USER=marian DB_PASSWORD=devpass DB_HOST=localhost.
## Owner decisions (keep)
Ranks and results are seen only by the school administrator and the deputies he appoints (not teachers or parents). A deputy can do everything the admin can EXCEPT appoint or remove deputies. Each school sets its own term dates. Logo: the redrawn Logo.jsx is the real logo (no original file exists). Cambridge scope: Lower Secondary (Stages 7-9) and IGCSE only.
## UNDONE (in order)
1. Before any real school: paid Render Postgres and paid web service (so it does not sleep), strong admin password, backups. Check UptimeRobot free-plan terms (may be non-commercial). Owner to set a phone reminder for early December (free Postgres expiry).
2. Security check on Render: DJANGO_DEBUG must be exactly False, and DJANGO_SECRET_KEY must be a newly generated key (the old one is in git history and counts as compromised).
3. Create schools and the first admin inside the app (today only in Django admin).
4. Parent and student screens (design talk first; they do not see ranks or results today).
5. Login extras are visual only, no backend: Google and Apple sign-in, Sign Up, Forgot password (needs a password reset flow), Remember me.
6. Teachers can read all marks and students of their own school through list endpoints, not only their assigned classes. Decide whether to restrict, and limit teacher screens to own classes.
7. Subject.definition is not validated against the school's curriculum.
8. Verify the IGCSE subject list against the official Cambridge list (Primary and AS/A Level deliberately deferred).
9. Owner to install the app on the phone and check the new icons, and confirm the login picture, ribbon background and fold animation live on Render.
10. Open rule question: report cards average opener, mid and end equally; change api/report_cards.py if the school wants weights.
11. Optional: class-wide subject trend endpoint for charts; early-warning screen (API exists, owner skipped the screen).
12. Last: offline sync, extra languages, AI learning and assessment features using ExamResult history.
