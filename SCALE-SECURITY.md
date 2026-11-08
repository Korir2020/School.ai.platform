# Scalability and security notes

This upgrade adds bounded list responses to fee structures, invoices, payments, learners, years, terms, report-card eligibility, and receipt selection. These endpoints return the existing page shape (`count`, `next`, `previous`, `results`) and cap requested page sizes through the shared pagination helper. The frontend's `listAll` helper now fetches all pages for the document-selection screen. Integrations that previously expected a bare JSON array from the converted fee-list endpoints must read `results` and follow `next`.

The school-admin home dashboard includes an examination → class → stream → subject → learner drill-down. It reports expected registered paper cells, completed outcomes, missing records, marks awaiting approval, workflow/outcome counts, and paginated learner paper statuses. “Missing” means no mark row; a saved pending disposition is shown separately. Numeric statistics use only approved/locked subject scores and follow the official paper weighting, absent-as-zero, and exempt/not-assessed exclusion rules. The drill-down API is school-admin-only and resolves examinations, rosters, registrations, and marks within the administrator's school.

Attendance rosters are paginated, and attendance writes validate the entire school-scoped batch before applying an atomic bulk upsert. Report snapshots now bulk-load cohort registrations, marks, enrollments, teacher assignments, and paper definitions instead of querying those tables separately for every learner. Exam ranking precomputes tie-aware competition ranks after sorting, avoiding a full-cohort scan for each result. Composite indexes support year/class rosters, student-year registrations, term/subject exam marks, and date-scoped attendance. Guardian child, fee, and report-card routes now verify the linked learner belongs to the guardian's school; the parent-account listing and creation paths also reject or hide cross-school links.

## Large export worker

Report-card and fee-receipt requests containing 50 or more records are written to the database-backed queue and return HTTP 202 with a job ID and status URL. Smaller exports remain synchronous. Report-card payloads for large jobs are built with a bounded set of cohort-wide queries rather than three per-learner queries. A batch is limited to 5,000 records. Authorized school administrators (and the same-school bursar for fee-receipt jobs) can read job status and download the artifact; other schools receive 404. Export artifacts are written outside `MEDIA_ROOT`, use owner-only file permissions, and are removed after seven days.

After applying migrations, run one or more independent worker processes:

```bash
cd backend
python manage.py run_background_jobs --poll-interval 2
```

The worker and web service must use the same database and share the same private artifact directory. Configure `DJANGO_BACKGROUND_JOB_ROOT` to a private persistent/shared volume when the services run in separate containers; the default is `backend/private_jobs/`. Do not point it at a public static/media directory. If the deployment platform cannot share a private filesystem between web and worker services, an object-storage backend must be configured before enabling cross-service exports; this code does not silently upload student records to a third party. Run the worker with the same environment variables and code release as the web service. PostgreSQL is recommended for production and concurrent workers (`skip_locked` queue claiming); SQLite is intended for development/tests and a single worker.

The queue currently covers the largest document batches (report cards and fee receipts). Ordinary small exports, exam publication, and analytics calculations are not converted into background jobs. Job errors are persisted for administrators/bursars and stale worker claims are recoverable after a heartbeat timeout.


## CBC Junior results (Grades 7–9)

The Junior CBC results path is scoped to CBC class levels numbered 7–9. Its catalogue endpoint returns learning areas only for the requested Junior grade; subject registration filters definition-bound subjects to the learner’s class level. The Junior framework and descriptor-scale APIs reject Primary/Senior ranges and non-CBC curricula. Grade-specific subject records keep paper maxima and weights independent across grades. No national Junior percentage bands are seeded in the framework or grading-scale UI: numeric grade bands and achievement wording are school-authored, and numeric report calculations use the exam’s frozen framework scheme when one is present.

Descriptor-only Junior exams publish only approved registered-learning-area outcomes, preserve the level-scale version used for the cohort, record publication/locking audit events, and expose class/stream descriptor distributions without numeric averages or ranks. CBC rankings default off and are enforced in result/report APIs as well as the UI; a school must enable the positions section to expose numeric rankings. Junior report cards are generated through the exam-based report module so school paper weights, assessment type, saved grades, learner comments, and the internal-school-not-KNEC notice are retained. The older unweighted term card redirects published Junior exams to that report module.

The existing 8-4-4 framework and its published calculations remain separate. This Junior implementation does not add Senior School pathways or assign learners to pathways.
