# Interactive exercises (Activity 17)

Exercises extend the practice quiz. Questions without a `type` key are the original
multiple-choice questions and behave exactly as before.

## Types (registry in `learning/exercise_types.py`)
- `short_text`: `accepted_answers` (1 to 10), matched after trimming, case folding and
  collapsing spaces.
- `numeric`: `answer` and `tolerance` as decimal strings, compared with exact decimal maths.
- Both carry `prompt`, `hint` (may be blank) and `explanation`.
- A new type (for example language practice) is one entry in `TYPES`: author-side fields and
  validation, a server-side check, and what to reveal. Endpoints do not change.

## Feedback and retries
- The first wrong attempt returns `correct: false` and the hint only.
- The accepted answer and explanation are revealed when the answer is correct or from the
  second submission for that resource version. Retries are unlimited within the existing
  hourly quiz throttle. Every attempt is scored on its own.

## Privacy and security
- Answer keys never reach the learner. The learner view of an exercise has `options: []`
  so older screens do not break.
- Typed answers are checked and discarded. Only the keyed fingerprint is stored, so no
  free text is kept in attempts, feedback or activity events.
- Attempts use the same UUID idempotency, throttle, evidence event and step-confirmation
  rule as quizzes. Results are practice, not exam marks.

## Not included
Teacher Studio authoring screens for exercises, the learner screen for typed answers,
language-practice type, coding sandbox, projects and submissions.
