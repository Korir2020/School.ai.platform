# Administrator final subject marks

This upgrade adds a separate, exam-scoped direct-final-subject-mark workflow for school administrators. It is intentionally separate from `Performance`, so teacher paper rows, `SubjectPaper` weights, and existing paper-based calculations are not changed.

## Workflow

1. Choose a draft examination and a registered subject in the school-admin **Marks** area.
2. Enter a numeric mark from 0 to 100 for each actively enrolled learner, or leave the learner as an explicit pending/non-scored disposition.
3. Save the batch as drafts, submit each row, and approve it with a reason.
4. Publish the examination through the existing administrator-only publication endpoint. Approved direct final marks are used as the subject score, bypassing paper components for that student/subject, then locked with audit entries.

The API validates school ownership, draft-exam state, active enrollment, academic-year subject registration, mark range, duplicate student entries, and non-scored dispositions. Locked rows cannot be changed. Submitted or approved corrections require a reason and approved corrections return to submitted status.

## Endpoints

- `GET /api/final-subject-marks/?exam=<id>&subject=<id>` — school-scoped final marks.
- `POST /api/final-subject-marks/` — administrator batch draft save with `{exam, subject, entries:[{student, marks, mark_status}]}`.
- `POST /api/final-subject-marks/<id>/submit/` — submit a draft.
- `POST /api/final-subject-marks/<id>/approve/` — approve with a decision reason.
- `POST /api/final-subject-marks/<id>/reject/` — return to draft with a decision reason.
- `POST /api/final-subject-marks/<id>/lock/` — lock after approval.

Existing teacher marks endpoints and paper workflows remain unchanged.
