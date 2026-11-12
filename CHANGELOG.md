# School AI Platform — Changelog
## 2026-11-12
### Migration Centre (learner list import)
- Upload a register (Excel, CSV, TSV or typed PDF) or paste the table; nothing is saved until the administrator confirms.
- Column recognition covers common headings, including Swahili (Namba ya Kuingia, Jina Kamili, Darasa); unknown headings are matched by hand, one column at a time.
- Rows are classified as ready, needs confirmation, needs fixing, already in Marian or skipped, with a reason in plain language on every row.
- Fixes and decisions live in the import only: the original file is never changed. Corrections can be made per row or for the whole selection, and a class can be chosen once for a file with no class column.
- Grade 10-12 learners need an assessment number before they can be imported; a learner without an admission number gets a marked temporary one.
- Repeating an import never adds a learner twice: admission numbers and names are checked against Marian and against the file itself.
- Import is idempotent per request id, and the whole commit is one transaction with an audit entry (school, user, counts, classes, temporary numbers).
- api/migration_rules.py, api/migration_check.py, api/migration_commit.py, frontend/src/MigrationCentre.jsx, frontend/src/migration.css, tests in api/test_migration_*.py

## 2026-09-22

### Project Started
- Created the GitHub repository.
- Created AI_CONTEXT.md.
- Created ARCHITECTURE.md.
- Created DECISIONS.md.
- Established the initial project vision and architecture.

## B4 - Setup wizard backend
- GET /api/setup/ (checklist: profile, academic year, term, stream, subject)
- POST /api/setup/complete/ (full admins only, atomic, audited, idempotent)
- /api/auth/me/ now returns setup_complete
- api/setup_views.py, api/test_setup.py
