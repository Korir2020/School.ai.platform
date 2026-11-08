# CBC Junior (Grades 7–9) manual acceptance test

This guide covers the CBC Junior work only. It uses school-authored assessment and grading settings. The sample grade bands and descriptor wording below are test data, not national or KNEC rules. A school should replace them with its approved policies before using real results. Junior pathways are not configured here; Senior School pathways remain out of scope.

## 1. Prepare test data

Use a test school and create or select:

- Curriculum: `CBC` / Competency-Based Curriculum.
- Academic year: `2026`.
- Term: `Term 1`.
- Class: `Grade 7` and stream: `East`.
- Learners:
  - `Amani Otieno`, admission number `JUN-001`.
  - `Brian Kamau`, admission number `JUN-002`.
- Enroll both learners in Grade 7, East, for 2026.

In **Setup → Classes and subjects → Add CBC Junior learning area by grade**, select Grade 7 and add the catalogue entries for Mathematics and English. The subjects created this way are grade-specific. If you also create Grade 8 or Grade 9 learning areas, they are separate subject records with their own paper setup.

In **Subject Registration**, choose each learner’s 2026 Grade 7 enrollment and register both Mathematics and English as compulsory. The selector should show only subjects defined for that learner’s selected grade, plus school-created subjects that are not restricted to another grade. Unregistered learning areas must not be counted in examination results or report cards.

## 2. Configure the school rules

In **Grading Scale**, enter this sample school scale:

| School grade label | From % | To % | Points |
|---|---:|---:|---:|
| Developing | 0 | 60 | 1 |
| Meeting | 60 | 75 | 2 |
| Extending | 75 | 100 | 3 |

Set pass mark `60`, decimal places `1`, rounding `half_up`, mean rule `total_over_max`, absent policy `pending`, and leave “Best N subjects” empty. These values exist only to make the demonstration’s outcomes deterministic; they are not official national thresholds.

In **Report Cards → CBC Junior achievement descriptors**, save a Grade 7–9 descriptor version using school-authored examples such as:

| Internal key | Sample school label | Sample school description |
|---|---|---|
| `beginning` | Beginning | Needs further guided practice. |
| `progressing` | Progressing | Applies some skills with support. |
| `meeting` | Meeting | Demonstrates the school-defined target. |
| `extending` | Extending | Applies learning independently in new contexts. |

In **Framework administration**, create and assign `CBC Junior (Grades 7–9; school-configured)` to the CBC curriculum and Grade 7 (and the relevant academic year). Freeze the school grading scale for the version if the interface offers that option. The framework editor should restrict CBC Junior to Grades 7–9. No Marian-supplied Junior percentage bands should appear.

## 3. Configure papers and enter the sample numeric marks

In **Setup → Paper Setup**, configure:

| Learning area | Paper | Maximum mark | Weight |
|---|---:|---:|---:|
| Mathematics — Grade 7 | Paper 1 | 50 | 50% |
| Mathematics — Grade 7 | Paper 2 | 100 | 50% |
| English — Grade 7 | Paper 1 | 100 | 100% |

Create a school assessment named **Grade 7 Weighted School Assessment** for Grade 7. In the teacher marks workflow choose that exam, Grade 7, East, then the assigned subject. Enter and submit these marks:

| Learner | Mathematics P1 | Mathematics P2 | English P1 |
|---|---:|---:|---:|
| Amani Otieno (`JUN-001`) | 40 / 50 | 60 / 100 | 80 / 100 |
| Brian Kamau (`JUN-002`) | 30 / 50 | 70 / 100 | 70 / 100 |

Submit the marks batch as the teacher. As an administrator, review and approve the submission using a reason, then publish the examination.

### Expected calculations

- Amani Mathematics: `(40/50 × 50) + (60/100 × 50) = 70%`, school grade **Meeting**.
- Amani English: `80%`, school grade **Extending**.
- Amani overall mean: `(70 + 80) / 2 = 75%`, school grade **Extending**.
- Brian Mathematics: `(30/50 × 50) + (70/100 × 50) = 65%`, school grade **Meeting**.
- Brian English: `70%`, school grade **Meeting**.
- Brian overall mean: `(65 + 70) / 2 = 67.5%`, school grade **Meeting**.

Open the published examination’s **Results**. It should show the school-configured overall and subject grades alongside percentages. CBC Junior class/stream rankings are disabled by default; they should appear only if the school explicitly enables the positions section in report policy.

## 4. Print and inspect the numeric report cards

Open **Report Cards**, select the published Grade 7 weighted assessment and Grade 7 class. Check that the learner selection/readiness reports both learners complete. Preview or download each report card.

Verify that each card uses the configured paper weights, shows subject percentages/grades and the school-configured overall result, includes the report’s configured teacher comments where present, and carries an internal school-assessment notice. The card must not describe the result or positions as an official KNEC result or ranking. The legacy term-only report-card route should direct Grade 7 users to the exam-based report module instead of recalculating an unweighted average.

## 5. Test the Junior descriptor-only report card

Use a clean term (for example, Term 2) with no numeric `Performance` records already entered for the same learners and assessment type. Numeric marks and descriptor-only outcomes are stored by term/assessment type, so do not reuse the numeric-mark term/type for this descriptor-only check. Set that term active and create a Grade 7 exam with no numeric marks. In the teacher level-entry workflow, enter one school-defined achievement level for every registered learning area and learner. Sample outcomes:

| Learner | Mathematics | English | Teacher comment examples |
|---|---|---|---|
| Amani | Meeting | Extending | “Uses evidence to explain a solution.” / “Communicates ideas clearly.” |
| Brian | Progressing | Meeting | “Applies strategies with support.” / “Explains the main idea.” |

Submit/review the level entries using the available approval workflow. An administrator must publish only after all registered learning areas have an approved outcome. The scale version used for the cohort should be consistent; publication should remain blocked for missing learning areas or mixed descriptor versions.

In the published exam results, verify that:

- The mode is labelled as school-defined achievement levels.
- Each learner has a label-based overall progress summary and subject levels.
- Class and East-stream descriptor distributions are shown.
- Numeric averages, numeric ranks, and KNEC claims are absent.

In **Report Cards**, select the descriptor-only exam. Confirm both learners are complete, then preview/download each card. It should show the Junior learning-progress heading, the school-defined level and descriptor explanation for each registered learning area, teacher comments, and a class-level distribution summary. It must clearly state that this is an internal school assessment, not an official KNEC assessment, and must not show numeric averages or rankings.

## 6. Verify zero is not absence

In a separate numeric test assessment, enter `0` for a scored paper and save it with status **scored**. Confirm the UI and result treat it as a real zero mark and apply the configured school grading rules. For a separate learner/paper, select **absent** instead; it must display as absent, not as a scored zero. Also inspect the distinct **exempted**, **not assessed**, and **pending** states if available in the teacher marks-entry workflow.

## 7. Regression checks

- Grade 6 subjects/scales still use CBC Primary settings; Junior descriptors are limited to Grades 7–9.
- Grade 10 and above are not offered the Junior catalogue or Junior framework.
- An exam with no applicable school grading scale must not invent percentage bands to publish CBC numeric grades.
- Existing 8-4-4 reports and KCSE calculations remain on their existing framework and are not converted to CBC rules.
