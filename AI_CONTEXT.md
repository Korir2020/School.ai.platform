# Marian (School.ai.platform) - Handoff Guide

Multi-school Django 6.1 + DRF + SimpleJWT school management and AI learning platform, meant for commercialization.
Owner is a beginner working in GitHub Codespaces on a phone. Give very brief steps, one action at a time, with the exact terminal location. Review existing code before changing it. Never assume a feature is complete without evidence. Security, data integrity and tests come before speed. Finish the backend before the frontend.

## Run it
- Folder: /workspaces/School.ai.platform/backend
- Tests: python manage.py test   (all passed at the last commit)
- Server: python manage.py runserver
- Catalogues into a fresh DB: python manage.py loaddata schools/fixtures/catalogues.json
- Env vars (production): DJANGO_SECRET_KEY, DJANGO_DEBUG (True/False), DJANGO_ALLOWED_HOSTS (comma list)
- Layout: config/ (settings, urls), schools/ (models, migrations to 0023), api/ (views, serializers, permissions, workflow, analytics, papers, exams, exam_publish, audit, report_cards, auth_views, tests.py)

## Rules
- Shared curriculum definitions stay separate from each school's subjects.
- Every feature: model > migration > serializer > API view > URL > permissions > tests.
- Preserve existing records. No duplicate structures.
- Roles: superadmin (is_superuser), school admin (SchoolAdminProfile), teacher (TeacherProfile). Helpers: _scope() in api/views.py, get_user_school_id() in api/permissions.py.
- Other-school records return 404; wrong role returns 403; anonymous returns 401.

## Models (schools/models.py)
School, Student, AcademicYear, Term, Curriculum, ClassLevel, Stream, Enrollment, Subject, Performance (marks 0-100, status draft/submitted/approved/locked, entered_by, paper_number), TeacherProfile, TeacherAssignment (teacher+subject+stream), SchoolAdminProfile, SubjectDefinition, CurriculumPathway, MarkAuditLog, SubjectPaper (subject, paper_number, weight), Exam (school, term, assessment_type, class_level, draft/published), ExamResult (exam, student, overall_average, stream_rank, class_rank, subject_scores).

## Endpoints
- Auth: POST /api/auth/login/, /api/auth/refresh/, GET /api/auth/me/
- School-scoped GET lists: /api/schools/ students/ academic-years/ terms/ streams/ enrollments/ subjects/ (curriculums/ and class-levels/ are shared)
- Marks: GET/POST /api/performance/ (teacher must be assigned; starts as draft), PATCH /api/performance/<id>/ (edit draft only), POST /api/performance/<id>/<submit|approve|reject|lock>/
- Audit trail: GET /api/audit-logs/ (admin; optional ?performance=id)
- Report card: GET /api/report-card/<student>/<term>/ (approved/locked marks only)
- Analytics: GET /api/analytics/term-summary/<term>/ (admin). If api/analytics.py also has stream_ranking, it is an old per-term ranking, replaced by exam publishing: safe to remove.
- Paper weights: GET/POST /api/subject-papers/ (admin posts; total per subject cannot exceed 100)
- Exams: GET/POST /api/exams/ (admin posts), POST /api/exams/<id>/publish/

## Ranking design (owner's requirement)
Ranking is per complete exam (all papers, e.g. Paper 1, 2, 3), not automatic each term. The school admin presses publish. Papers have admin-set weights totalling 100. Publish refuses if any paper is missing or not approved. It then computes weighted subject scores and each student's overall average, ranks in stream and class level (ties share a rank), stores one ExamResult per student (subject_scores optional extra), locks the marks used, and writes audit entries. Overall results are for tracking progress over time.

## Done
Auth and roles, school isolation on all list APIs, teacher assignments gating marks entry, mark workflow with audit, report cards, term analytics, paper weights, exams, publish with tests, CBC catalogue checked against KICD Senior School design (PE, Advanced Maths, Advanced English added), env-based settings.

## Remaining backend (priority order)
1. Admin create/update APIs: only performance, papers and exams are writable via API today. Schools, students, years, terms, streams, enrollments, subjects and teacher assignments are created through Django admin only.
2. GET exam results API (per exam, and a student's history across exams) with visibility rules; put published rank/overall on report cards.
3. Edit/delete SubjectPaper; block weight changes once an exam using them is published.
4. More role edge-case tests across all endpoints.
5. Verify 8-4-4 and Cambridge catalogues against official sources (CBC done; Forms 3-4 are the last 8-4-4 cohort; consider Kenya Sign Language).
6. Dashboards/analytics, then AI learning, assessment and early-warning features using ExamResult history.
7. Production readiness: rotate SECRET_KEY (old one is in git history), DEBUG off, PostgreSQL instead of sqlite, HTTPS settings, CORS for the frontend, pagination, login rate limiting, API docs, backups, monitoring.

## Frontend (after backend is solid)
Responsive for low-end Android phones and computers: Marian branding, animated pre-login screen, login, role dashboards, management screens, mark entry, report cards, analytics, notifications, offline-first sync, then multilingual and AI features.

## Starter message for a new chat
"I am building Marian, a multi-school Django school platform. Read AI_CONTEXT.md from my repo (I will paste it). Continue from Remaining backend item 1. Do not restart or duplicate models. Give brief step-by-step instructions, one action at a time, with the exact terminal location."
