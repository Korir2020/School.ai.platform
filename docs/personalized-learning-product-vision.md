# MARIAN PERSONALIZED LEARNING

## Product Vision — Part 1

### Product purpose

Marian Personalized Learning is an independent learning environment within the Marian ecosystem. Its purpose is to help people discover knowledge, build skills, explore interests, practise, create, and pursue personal development through learning that is personalized, interest-driven, and self-directed.

It serves both **curriculum-based learning** and **learning beyond the curriculum**. It is a learning product—not an extension of examination analytics, learner portfolios, academic weakness detection, or school administration and finance workflows.

### Product vision

Create one intelligent, engaging learning environment where students, teachers, school administrators, and independent public learners can choose meaningful learning, explore trusted resources, develop at their own pace, and create work that reflects their interests and goals.

### Confirmed product decisions

These are product constraints, not provisional suggestions:

| Decision | Product direction |
|---|---|
| Access | Students, teachers, and administrators can all learn. Job title must not restrict access to subjects or beyond-curriculum categories. Independent public learners are also supported. |
| Account types | Support both school-managed accounts and independent public accounts, with distinct permissions and data boundaries. |
| Learning approach | Personalized, interest-driven, self-directed, and adaptable to each learner's selected interests, goals, preferred formats, and difficulty. |
| AI | Integrate AI capabilities throughout the learning ecosystem where technically supported and safely configured. Do not represent unavailable providers or credentials as working functionality. |
| Content | Include Marian-created materials and approved external resources. Identify origin, rights, attribution, and language clearly. |
| Curriculum | Support configurable Kenyan CBC Grades 1–12, Cambridge pathways, and broader international knowledge; do not hardcode one curriculum structure. |
| Languages | Build multilingual capability from the beginning, prioritizing English and Kiswahili, with future expansion. Keep original content distinguishable from translations. |
| Certificates | Do not issue certificates in the initial product. |
| Offline | Design interfaces and data structures with future offline learning in mind; do not claim or implement full offline learning in this initial phase. |
| Academic weakness profiling | Excluded. Do not use exam weakness detection, negative academic labels, or examination marks to drive this product's personalization. |

### Intended learners and experience principles

- **Students** should be able to discover, practise, build, and follow learning journeys appropriate to their age and chosen interests. They should have control over preferences and be able to dismiss or change recommendations.
- **Teachers** should be able to learn for their own development and explore any subject; their professional role does not limit their personal learning. Teaching and resource-creation tools may be added as separate capabilities.
- **Administrators** should be able to learn like other users and, through separately permissioned administration tools, govern school learning settings and approved content. Administrative visibility must not imply unrestricted access to independent learners' private activity.
- **Independent public learners** should have an account and learning experience that is separate from school tenancy and school-managed learner records.

All experiences should value curiosity and learner agency. Recommendations are suggestions, not compulsory assignments. Motivation features must encourage genuine learning and avoid mandatory public rankings or rewards for meaningless clicks and time spent.

### Product boundaries

Personalized Learning must be a dedicated product domain with its own learning data, APIs, learner interface, content operations, activity/progress records, AI orchestration, and administration capabilities. It may reuse Marian identity, school tenancy, curriculum references, and common UI components through explicit, least-privilege integrations.

It must not depend on or modify:

- examination marks, calculations, approval, or publication;
- academic weakness detection or early-warning labels;
- report generation or archived reports;
- existing learner portfolio functionality;
- school fee billing or payment workflows; or
- official academic records as a substitute for learning activity data.

### Vision-level outcomes

The product vision is successful when people can choose what and how to learn; find both curriculum-aligned and wider-interest materials; set and revise goals; make visible progress through meaningful learning activities; receive useful, controllable recommendations; and do so in a multilingual, accessible experience with privacy and age-appropriate safeguards. These are intended product outcomes, not claims that features have already been implemented.

### What this brief does not authorize or claim

This Part 1 document records the product vision and confirmed decisions. It does not itself approve a detailed data model, select an AI provider, authorize transmission of learner data to third parties, define consent/retention policy, promise certificates, or claim that offline learning or any other feature is already available. Those items require design, security review, technical validation, and appropriately staged implementation.
