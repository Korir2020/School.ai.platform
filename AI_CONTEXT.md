# Marian (School.ai.platform) - AI Context

Multi-school Django + DRF school management and AI learning platform.
Rule: shared curriculum definitions stay separate from each school's subjects.
Feature order: model > migration > serializer > API view > URL > permissions > tests.

## Done (backend)
- Core models, curriculum catalogues, subject definitions/pathways, migrations to 0022.
- JWT auth (/api/auth/login, refresh, me); roles: superadmin, school admin, teacher.
- School isolation on list APIs; teacher assignments (subject + stream).
- Marks: create (draft), edit draft (PATCH /api/performance/<id>/),
  workflow submit/approve/reject/lock, audit log (/api/audit-logs/),
  report card (/api/report-card/<student>/<term>/, approved/locked only).
- Validation: marks 0-100, term must belong to academic year.
- Tests: isolation, marks entry, JWT, workflow, report cards, edit, audit, term check.

## Remaining backend
- Verify 8-4-4 and Cambridge catalogues against official sources (CBC verified; Forms 3-4 are the last 8-4-4 cohort).
- More role edge-case tests, analytics/dashboards, then AI features.
- API docs, backups, monitoring, secure deployment.
- Then frontend (phone-first, offline-first).


## Also done
- CBC catalogue checked against KICD Senior School design; added PE, Advanced Maths, Advanced English.
- Catalogue fixture: schools/fixtures/catalogues.json (load with loaddata).
- Isolation tests cover all 8 school-scoped endpoints.
- Settings read DJANGO_SECRET_KEY, DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS from environment.
- db.sqlite3 is not tracked by git. Old secret key is in git history: never use in production.
