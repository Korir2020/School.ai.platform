# Activities 13–14 merged into the main Personalized Learning project

The user clarified that the Activities 13–14 package must first be merged into the main project package, after which work should stop for the next instruction (Activity 15). The refreshed project starts from the main `Marian_Personalized_Learning_Independent_Subscript(1).zip` source and overlays the changed/new source from `Marian_Personalized_Learning_Activities_13_14.zip`. Both uploaded ZIPs and the primary Marian repository are unchanged.

The archive comparison found 10 modified shared project files, 11 new files, and 73 main-only files. The 10 changed files and nine safe new source/documentation/migration/test files were applied. The 73 main-only files were retained; no files were deleted. Two new `backend/private_jobs/.../receipt-00001.pdf` job-output files in the Activities 13–14 archive were deliberately omitted because they are private generated artifacts, not application source. The merge includes the Teacher Learning Studio, school-scoped Learning Centre, learner recommendations inbox, settings/authorization, migrations `learning.0008` and `learning.0009`, and the relevant tests/docs. No Activity 15, 16, 17, or 18 implementation is included.

## Validation in the merged copy

- `python manage.py check` — passed, no system-check issues.
- `python manage.py makemigrations --check --dry-run` — passed, no migration drift.
- `python -m compileall -q learning schools api` — passed.
- `python manage.py test learning.test_staff_learning_api learning.test_content_api --verbosity=1` — 24 tests; 23 passed and one SQLite row-lock/concurrency test skipped because SQLite lacks `SELECT FOR UPDATE`.
- Frontend Node tests — 15 passed.
- Vite production build — passed.
- Frontend lint — 0 errors and 78 project warnings, matching the recorded baseline.

Tests used a disposable SQLite test database. No application/production database was migrated, no content was published, and no deployment or production activation was performed. The skipped row-lock case must be run against a PostgreSQL-like test backend before production rollout. Catalogue publication remains hard-gated under Activity 9's policy decisions. The next canonical activity is Activity 15; the user requested that work pause here.
