# Path-step confirmation (Activities 8 and 17)

A quiz attempt is evidence of learning, never automatic completion.

## Rule
- A path step may use the completion rule `quiz_pass` (default pass mark 70%) or
  `quiz_pass:N` (N from 1 to 100). The rule is valid only for a resource step whose
  resource has a practice quiz.
- After a stored attempt, the server computes the percentage from the stored counts.
  If the learner has started the current path version and meets the pass mark, a
  `LearningStepCompletion` row is created as `awaiting_confirmation`.
- The path state (`LearningPathParticipation`) is unchanged by this feature.
  Completing a whole path from confirmed steps is a separate policy decision.
- A failed hook never loses the stored attempt.

## Teacher confirmation (school learners)
- `GET /api/learning/v1/teacher/step-confirmations/` lists up to 200 awaiting steps for
  the teacher's assigned learners. It shows name, resource title, step, and the time the
  pass mark was met. It never shows answers, scores, correctness or feedback.
- `POST .../step-confirmations/<id>/decision/` with `confirm` or `reject`. Reads and
  decisions are audited. A rejected step returns to awaiting after a new passing attempt.
- Uses the existing `TeacherLearningStudio` permission and assignment checks.

## Independent learners (no teacher)
- A repeat pass on a later calendar day at the pass mark plus 10 points (maximum 100)
  confirms the step as `repeat_practice`. No staff member sees any learner data.
- `LEARNING_INDEPENDENT_REPEAT_VERIFICATION=False` turns this off. Steps then stay
  awaiting until an approved reviewer route exists.
- Pending owner approval of this design.

## Not included
No screens yet, no path completion rule, no mentor or moderator route.
