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
- Verify curriculum catalogues against official requirements.
- Wider tests (all list APIs, role edge cases), analytics, AI features.
- API docs, backups, monitoring, secure deployment.
- Then frontend (phone-first, offline-first).

## Housekeeping to do
- Remove stray backend/models.py, views.py, .py, *.bak and *.save files.
