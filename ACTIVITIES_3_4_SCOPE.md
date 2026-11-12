# Activities 3, 4 and 5 — accepted scope

Source: uploaded `Marian_marks_entry,_CBC_and_examination-report_aud(1).md`, sections 4–7 (audit of the project archive at `/home/ubuntu/upload/School.ai.platform-main(62).zip`). This file records the exact requested implementation scope so later revisions retain the distinction between school-authored results and national assessment reporting.

## Activity 3 — CBC reports

Implement and test separate CBC report designs by stage (Primary, Junior and Senior) and by result mode (numerical marks and achievement levels). Include learner identity, appropriate learning-area/subject rows and recorded progress. Senior reports must include pathway and registered subject combination. Achievement-level reports must include level-aware teacher feedback and improvement suggestions. Identify school-authored configurations as internal school reporting; do not claim the templates are KNEC formats or official KNEC results.

## Activity 4 — comments

Add neutral, editable, scale-aware default comments for subject-teacher, class-teacher and headteacher/principal fields. Do not assert unverified personal observations. Make the existing authoring roles usable with appropriate permissions. The nonfunctional AI drafter must either be correctly configured or removed/disabled.

## Source context and original references

The uploaded audit notes that the CBA framework recommends qualitative and quantitative learning-area information and broad performance levels with strengths and suggested improvement strategies. Those principles do not establish that Marian's school reports are official or use a nationally prescribed layout. The audit's original references are:

1. KICD, *Basic Education Curriculum Framework (2019)*: https://kicd.ac.ke/wp-content/uploads/2019/08/BASIC-EDUCATION-CURRICULUM-FRAMEWORK-2019.pdf
2. KNEC, *Competency Based Assessment Framework*: https://www.knec.ac.ke/wp-content/uploads/2021/06/CBA-Age-Based-Regular-Framework.pdf
3. KNEC, *KJSEA Regulations 2026*: https://www.knec.ac.ke/wp-content/uploads/2026/02/KJSEA-REGULATIONS.pdf
4. KNEC, *School Report Guide*: https://www.knec.ac.ke/knec-school-report-guide/index.html

Implementation preserves the app's label that its CBC term/exam results are internal school assessments and not official KNEC reports.

## Implementation and validation (12 Nov 2026)

- Numerical CBC PDFs now use stage-specific Primary, Junior and Senior report layouts, including recorded scores, the school's grading scale, learning-area feedback and prior published progress. Senior reports include the learner's pathway and registered subject combination.
- Achievement-level PDFs use distinct Primary, Junior and Senior layouts, show school-defined descriptors and teacher feedback, and include a possible next learning step. They print only approved/locked level records and do not invent marks, averages or ranks. Earlier descriptors are limited to prior approved/locked records for the same learner and subject.
- Report comment defaults are editable by an administrator and keyed to the school's numeric or CBC achievement scale. Subject suggestions describe recorded results; class-teacher and headteacher/principal wording remains a draft suggestion until a learner-specific comment is saved and approved. Class teachers can author only the permitted class-teacher remark in their assigned scope; administrators retain approval and principal-comment control. The nonfunctional AI-draft action is removed.
- Validation: 22 focused Django tests passed on the isolated SQLite test database; 7 frontend Node tests passed; frontend lint completed with 0 errors (76 warnings across the project); Vite production build and Python syntax compilation passed. No production database or student records were changed.

## Activity 5 — exam identity, immutable reports and regressions (12 Nov 2026)

The requested Activity 5 outcome is to link each published report to a unique exam identifier; preserve a durable immutable published PDF/version when exact reproduction is required; and add PDF-content/layout assertions alongside role, multi-exam and CBC-stage tests.

- Numerical and achievement-level report PDFs now print the exam-qualified reference `RPT-E<exam_id>-<admission_number>`. Numeric CBC verification keeps its QR/token flow; level-based PDFs print their reference and verification code. The public verification endpoint accepts the exam-qualified format, confirms that an optional exam ID matches, verifies immutable archives against their saved token, and retains compatibility with prior report numbers.
- A first successful PDF request for a published exam/learner pair stores the exact PDF bytes, SHA-256, source digest, verification token, report mode and renderer version in a new `PublishedReportArtifact` database row. A uniqueness constraint allows only one issued artifact per exam/learner; protected foreign keys and immutable model methods prevent ordinary update/delete operations. Subsequent authorized requests return the stored bytes, even if current marks/comments or grading settings change. Authorization is evaluated before archive delivery.
- Regression tests verify guardian/teacher/school boundaries after a file has been archived; exact numeric and CBC-level PDF content and exam references; immutable bytes/checksums and verification after live-source/settings changes; distinct report references for two exams of the same learner; and Primary/Junior/Senior CBC layout identity. The stage PDFs are inspected via extracted text, not only byte signatures.
- **Historical limitation:** the project had no PDF archive before this migration, so prior PDFs that were never stored cannot be reconstructed byte-for-byte. A published report is archived the first time it is successfully generated/requested after this upgrade; that issued version is then immutable and reproducible.
- The additive schema migration is `backend/schools/migrations/0073_published_report_artifact.py`. Validation: 37 focused Django tests passed against the isolated SQLite test database; Python compilation and trailing-whitespace checks passed for all changed Python files. No production database or student records were changed.
