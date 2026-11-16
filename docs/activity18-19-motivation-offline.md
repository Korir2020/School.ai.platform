# Activities 18–19 implementation

This document records the independent implementation delivered in this source copy. It does not enable AI, public rankings, automatic path completion, certificates, or offline academic records.

## Activity 18

Motivation is personal and optional. Milestones and challenges are derived from explicit learner activity and own goal state. The UI supports English/Kiswahili labels, contrast and reduced motion controls, keyboard focus, responsive layout, and clear loading/empty/error/status states. School analytics are aggregate, school-scoped, and minimum-necessary.

## Activity 19

A learner selects currently visible published resources/paths, requests a seven-day package, and encrypts the manifest in the browser using AES-GCM. The package is stored in IndexedDB and is bound to the device identifier. Sync accepts only idempotent operations for package items; invalid or out-of-package operations are returned as conflicts. Packages can expire or be revoked.

The existing teacher-marks offline workspace uses its own encrypted store and queue. It is intentionally not reused or relabelled as Personalized Learning offline.
