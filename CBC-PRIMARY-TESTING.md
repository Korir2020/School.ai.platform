# CBC Primary (Grades 1–6) — Manual Acceptance Test

This acceptance test covers the CBC Primary path only. CBC Junior Grades 7–9 have a separate acceptance guide in `CBC-JUNIOR-TESTING.md`; Senior School remains out of scope. This guide uses school-configured rules and does not define or claim national KNEC grading thresholds. The existing 8-4-4 calculation path is unchanged.

## 1. Set up a test class and learners

Using an administrator account, create or select:

- Curriculum: **CBC**
- Class: **Grade 3**
- Stream: **East**
- Academic year: **2026**
- Term: **Term 1**

Use the CBC Primary learning-area catalogue in **Setup** to create Grade 3 subjects **Mathematics — Grade 3** and **English — Grade 3**. Enroll these two learners in Grade 3 East and register both subjects as compulsory for academic year 2026:

| Admission number | Learner | Mathematics | English |
|---|---|---:|---:|
| PRI-001 | Amani Otieno | Registered | Registered |
| PRI-002 | Brian Kamau | Registered | Registered |

Confirm each learner’s subject registrations before entering marks. Unregistered learning areas are intentionally excluded from the report and overall result.

## 2. Configure a school assessment and paper weights

Create a **school assessment** for Grade 3 (for example, **Grade 3 Term 1 Weighted Assessment**) and configure its paper structure:

| Learning area | Paper | Maximum mark | Weight |
|---|---:|---:|---:|
| Mathematics — Grade 3 | 1 | 50 | 40% |
| Mathematics — Grade 3 | 2 | 100 | 60% |
| English — Grade 3 | 1 | 100 | 100% |

Each learning area’s configured paper weights must total 100%. Do not select an official KNEC assessment for this sample; the result is an internal school assessment.

In the CBC Primary framework configuration, select the **CBC Primary Grades 1–6** framework and assign it to Grade 3 for 2026. In the school grading configuration, enter school-approved example bands (these are test values, not national rules):

| School grade label | Minimum percent | Maximum percent | Points |
|---|---:|---:|---:|
| Developing | 0 | 59.99 | 1 |
| Meeting | 60 | 74.99 | 2 |
| Extending | 75 | 100 | 3 |

For a simple expected average, set the school’s mean rule to **total over maximum**, leave **best N** unset, choose a rounding precision of 1 decimal place, and set the school’s pass threshold to 60%. Choose the school’s own absent policy. These choices are examples for the test and are editable by the school.

## 3. Enter and verify sample marks

Enter marks for both learners, saving the batch as a draft before submitting it. Use these values:

| Learner | Mathematics Paper 1 (out of 50) | Mathematics Paper 2 (out of 100) | English Paper 1 (out of 100) |
|---|---:|---:|---:|
| Amani Otieno (PRI-001) | 40 | 60 | 80 |
| Brian Kamau (PRI-002) | 50 | 80 | 70 |

Expected calculations:

- Amani Mathematics: `(40/50 × 100 × 40%) + (60/100 × 100 × 60%) = 68%` → **Meeting**.
- Amani English: `80/100 × 100 = 80%` → **Extending**.
- Amani overall: `(68 + 80) / 2 = 74.0%` → **Meeting**.
- Brian Mathematics: `(50/50 × 100 × 40%) + (80/100 × 100 × 60%) = 88%` → **Extending**.
- Brian English: `70/100 × 100 = 70%` → **Meeting**.
- Brian overall: `(88 + 70) / 2 = 79.0%` → **Extending**.

Submit the batch. As an administrator, review and approve it, entering a reason. Reopen the published results and verify the school-calculated subject percentages and overall results. CBC Primary rankings are **off by default**; no class or stream positions should be shown unless the school explicitly enables the positions section in report settings. If the school enables it, the published rankings use the configured school ranking and tie policy.

### Verify zero is not absence (optional)

In a separate draft assessment, enter **0** as a scored mark for one registered paper. Confirm it is displayed as a score of zero and is not marked absent. Separately select **Absent** for another learner/paper and confirm its status is shown as absent. Do not use an empty mark to represent either case.

## 4. Verify school-defined CBC achievement descriptors

As an administrator, add three **school-authored** Grade 3 descriptors under the CBC Primary achievement settings:

- **Starting** — “Needs more guided practice.”
- **Ready** — “Demonstrates the school-defined target.”
- **Strong** — “Applies learning independently.”

These names and explanations are sample school text, not national labels or thresholds.

Create a separate Grade 3 **mid-term** school assessment named **Grade 3 Term 1 Learning Areas Check**. For both learners, have the teacher enter one approved level for each registered learning area, with a short teacher comment:

| Learner | Mathematics | English |
|---|---|---|
| Amani Otieno (PRI-001) | Ready — “Explains strategies clearly.” | Strong — “Uses new vocabulary independently.” |
| Brian Kamau (PRI-002) | Strong — “Applies number strategies independently.” | Ready — “Reads and explains the main idea.” |

Submit and approve the assessment. The administrator must publish this descriptor-only assessment. The results view should show learner-level descriptors and class/stream descriptor distributions, with **no numeric average or numeric rank** and a notice that this is an internal school assessment, not an official KNEC result.

## 5. Generate and inspect report cards

Open **Report Cards**, select the published assessment and **Grade 3**, then choose **Check readiness**. Confirm both learners are ready. Preview or download each PDF.

For the weighted marks assessment, confirm the learning-area percentages, school-configured grades, overall result, paper breakdown if enabled, and the internal-school-assessment notice. For the descriptor-only assessment, confirm every registered learning area appears with its school-defined descriptor, explanation, and teacher comment; the report must not invent a numeric average or rank. The CBC Primary report must clearly state that it is not an official KNEC assessment.

## Acceptance checklist

- [ ] Grade-specific CBC catalogue creates only the Grade 3 learning areas selected.
- [ ] A learner’s individual academic-year registrations determine which learning areas count.
- [ ] Paper weights drive each learning-area percentage and school grade.
- [ ] Overall performance follows the school’s configured mean and grade rules.
- [ ] Zero and absent remain distinct statuses.
- [ ] Teacher batch submission and reasoned administrator approval are available and audited.
- [ ] CBC Primary numeric rankings remain hidden unless the school enables them.
- [ ] Descriptor-only publication has distributions and report cards without numeric averages or rankings.
- [ ] Reports identify these results as school assessments, not official KNEC assessments.
- [ ] Existing 8-4-4 calculations and reports continue to pass the regression suite.
