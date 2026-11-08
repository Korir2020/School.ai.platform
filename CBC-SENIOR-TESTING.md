# CBC Senior (Grades 10–12) — Manual Acceptance Test

This guide verifies Marian's Senior CBC examination, results and reporting workflow using school-configured rules. Sample grade bands and descriptor labels below are test data only; they are not national grading rules. Do not describe school assessments or their rankings as official KNEC results. Existing 8-4-4 calculations and reporting remain separate and unchanged.

## 1. Prepare the school, classes and pathways

Using a test-school administrator account, create or select:

- Curriculum: **CBC**.
- Academic year: **2026**; Term 1 and (for the descriptor-only test) Term 2.
- Classes: **Grade 9**, **Grade 10**, **Grade 11** and **Grade 12**.
- Grade 10 stream: **East**; Grade 9 stream: **West**.

In the Senior CBC catalogue/setup, make the following Grade 10 learning areas available. The school can substitute its own subjects; the key is that shared learning areas and pathway-specific areas are represented:

| Learning area | Available pathway(s) | Registration in this test |
|---|---|---|
| English | STEM, Social Sciences, Arts and Sports Science | All four learners |
| Physics | STEM | STEM learners only |
| History | Social Sciences | Social Sciences learner only |
| Music and Movement | Arts and Sports Science | Arts and Sports learner only |

Confirm that the available pathways are **STEM**, **Social Sciences**, and **Arts and Sports Science**. Create four test learners and enroll them in Grade 10 East for academic year 2026:

| Admission no. | Learner | Pathway | Registered learning areas |
|---|---|---|---|
| SEN-001 | Amani Otieno | STEM | English, Physics |
| SEN-002 | Brian Kamau | STEM | English, Physics |
| SEN-003 | Carey Njeri | Social Sciences | English, History |
| SEN-004 | Dara Wanjiku | Arts and Sports Science | English, Music and Movement |

In **Subject Registration**, select each individual learner's 2026 Grade 10 enrollment and register only the areas in the table. This is an individual, academic-year registration: the assessment and report should include only that learner's registered subjects that are valid for the selected pathway. A subject tagged for a different pathway must be rejected, even if it is mistakenly submitted in a registration or marks request.

## 2. Configure the Senior framework and school grading rules

In framework administration, create and assign the **CBC Senior (Grades 10–12)** framework to Grade 10 for 2026. Confirm that the framework cannot be applied to Grade 9 or a non-CBC curriculum. The CBC Senior framework does not provide Marian-invented percentage bands; configure the school's approved grading scale separately.

For a deterministic sample, use this school-authored scale (these are demonstration values, not KNEC thresholds):

| School grade | From % | To % | Points |
|---|---:|---:|---:|
| Developing | 0 | 59.99 | 1 |
| Meeting | 60 | 74.99 | 2 |
| Extending | 75 | 100 | 3 |

Set the school mean rule to **total over maximum**, decimal places to **1**, pass threshold to **60%**, and absent policy to **pending**; leave **Best N** unset. Configure the school's approved tie/ranking policy. In **Report Cards → section settings**, leave **positions** and **subject positions** disabled initially: Senior positions are hidden by default and must be explicitly enabled by school policy before ranks are reported.

## 3. Set up the school examination and enter numeric marks

Create a school assessment for Grade 10, Term 1, such as **Grade 10 Term 1 Pathway Assessment**. Configure one 100-mark paper at 100% for each of these Grade 10 subjects: English, Physics, History, and Music and Movement. If your school uses multiple papers, set the maximum marks and weights according to its own scheme and ensure each subject's configured weights total 100%.

In the teacher marks-entry workflow, select the examination, Grade 10, East stream, then each assigned subject. Check that the roster is limited to enrolled learners registered in that subject. Enter the following sample scores, all with status **scored**:

| Learner | English / 100 | Physics / 100 | History / 100 | Music & Movement / 100 |
|---|---:|---:|---:|---:|
| Amani Otieno (SEN-001, STEM) | 80 | 80 | — | — |
| Brian Kamau (SEN-002, STEM) | 70 | 70 | — | — |
| Carey Njeri (SEN-003, Social Sciences) | 90 | — | 90 | — |
| Dara Wanjiku (SEN-004, Arts and Sports Science) | 65 | — | — | 65 |

Save a draft, review it, and submit the marks batch. As an administrator, review and approve (or return with a reason, correct, and reapprove) the submission, then publish the examination. Verify that **0**, if tested, remains a scored zero; **absent**, **exempted**, **not assessed**, and **pending** remain distinct statuses.

### Expected calculations

Because the example has one fully weighted paper per registered subject and uses a total-over-maximum mean, the expected school results are:

| Learner | Subject results | Overall mean | Sample school grade |
|---|---|---:|---|
| Amani | English 80% (Extending); Physics 80% (Extending) | 80.0% | Extending |
| Brian | English 70% (Meeting); Physics 70% (Meeting) | 70.0% | Meeting |
| Carey | English 90% (Extending); History 90% (Extending) | 90.0% | Extending |
| Dara | English 65% (Meeting); Music and Movement 65% (Meeting) | 65.0% | Meeting |

These are school-configured calculations, not national grades. Unregistered or pathway-ineligible areas should not appear in a learner's exam result, overall mean, or report card.

## 4. Verify pathway-and-subject-combination rankings

First inspect the published exam results and report settings with positions still disabled. Confirm the results response/UI says rankings are disabled and no numeric ranks are presented. Then, only if consistent with school policy, enable **positions** and **subject positions** in report-section settings and reopen the results/report rankings.

The comparison groups are based on the **same pathway and identical registered subject set**, not simply the class:

- SEN-001 and SEN-002 both have STEM + `{English, Physics}`. Amani should rank 1 of 2 and Brian 2 of 2, assuming higher overall percentage ranks first.
- SEN-003 has Social Sciences + `{English, History}` and is ranked only against learners with that exact combination (1 of 1 in this sample).
- SEN-004 has Arts and Sports Science + `{English, Music and Movement}` and is ranked only against that exact combination (1 of 1 in this sample).

The report-module analytics should identify three distinct pathway/subject-combination groups. A learner in another pathway or with another subject set must never be included in their ranking denominator. These are internal school positions, not official KNEC rankings.

## 5. Verify school-authored achievement descriptors

In **Report Cards → CBC Senior achievement descriptors**, save a school-authored Grade 10–12 descriptor scale. For example:

| Internal key | Sample school label | Sample school description |
|---|---|---|
| `emerging` | Emerging | Developing the school-defined skills. |
| `secure` | Secure | Demonstrates the school-defined target. |
| `advanced` | Advanced | Applies learning independently. |

These labels and descriptions are examples, not national descriptors. Create a separate descriptor-only school exam in **Term 2** (or another clean term/assessment type without numeric marks for the same learners and assessment type). Enter one approved level for **each registered subject for each learner**, with a teacher comment. Example:

| Learner | English | Second registered subject | Example comment |
|---|---|---|---|
| Amani | Secure | Physics: Advanced | “Explains evidence and applies strategies independently.” |
| Brian | Secure | Physics: Secure | “Demonstrates the school-defined target.” |
| Carey | Advanced | History: Secure | “Uses sources to support an explanation.” |
| Dara | Secure | Music and Movement: Advanced | “Applies skills creatively and consistently.” |

Submit and approve the entries; publish only when the assessment is complete for all registered learning areas and uses the intended scale version. Verify that results show each learner's pathway, combination and subject descriptors/comments, plus class/stream descriptor summaries. A descriptor-only assessment must not show numeric averages or numeric ranks. It must be identified as an internal school assessment, not an official KNEC result.

## 6. Verify year-end promotion and CSV import

For promotion, create a 2027 academic year and a Grade 9 West learner. Preview year-end promotion to Grade 10. The preview should indicate a pathway is required and offer the three valid Senior pathways. Attempting to run the promotion without assigning a pathway should return a validation error and leave the source enrollment active. Assign STEM for that learner and rerun; verify the new Grade 10 enrollment records the selected pathway.

For CSV import, use a test file with headers:

```csv
first_name,last_name,admission_number,class_level,stream,pathway
Ivy,Import,SEN-CSV,Grade 10,East,ARTS
```

Preview it first, then commit. Confirm the created Grade 10 enrollment has the Arts and Sports Science pathway. Repeat with the `pathway` field blank; the import preview should report an error and must not create a learner. The import accepts the pathway code (`ARTS`) or its configured pathway name.

## 7. Generate and inspect the report cards

Open **Report Cards**, select the published Grade 10 Term 1 numeric exam and Grade 10, then choose **Check readiness**. Confirm that all four learners are complete. Preview or download each PDF. Verify:

- Each report includes the learner's pathway and exact registered subject combination.
- Only registered subjects appear, with paper results, school-configured subject grades and the school's overall mean/grade.
- If positions are enabled, any overall/subject position uses only the matching pathway and subject-combination group; if disabled, no ranks are shown.
- Teacher comments appear when supplied, and the report carries an internal-school-assessment / not-official-KNEC notice.

Repeat readiness and PDF checks for the Term 2 descriptor-only exam. Confirm school-defined descriptor labels, explanations and comments appear with no numeric average or rank. The report must not imply that a school position is an official KNEC position.

## Acceptance checklist

- [ ] The Senior framework/catalogue is limited to CBC Grades 10–12.
- [ ] Learners have an individual pathway recorded on their academic-year enrollment.
- [ ] Senior subject eligibility is checked against grade and pathway during registration and marks/level entry.
- [ ] Individual academic-year subject registrations determine which subjects count.
- [ ] Configured paper weights, school grade bands and mean rules drive numeric results.
- [ ] Zero, absent, exempted, not assessed and pending remain distinct.
- [ ] School-authored descriptors and teacher comments are available, with no invented national bands.
- [ ] Rankings are off by default and, when enabled, grouped by identical pathway and subject set.
- [ ] Promotion and CSV import require a valid pathway for a Grade 10+ enrollment.
- [ ] Printable reports state the pathway/subject combination and distinguish internal assessment from official KNEC assessment.
- [ ] The existing 8-4-4 examination, grading, calculation and reporting behavior is preserved.
