---
name: Feature request
about: Define one reviewable Binux CRM behavior and its learning goal
labels: enhancement
---

## Goal
What user problem does this issue solve? Name the menu destination and primary user.

## Current behavior
What does the application do today? Link the relevant route/template or related issue. Distinguish working behavior from display-only demo content.

## Expected behavior
Describe the user flow from start to finish, including empty, invalid, and error states. State which data is read or changed and who may do it.

## Data and lifecycle
- Fields and requiredness:
- Validation and duplicate behavior:
- Status/transition rules:
- Archive, trash, restore, or retention behavior (if applicable):
- External services or side effects (if applicable; otherwise say none):

## Acceptance criteria
- [ ] Each criterion is observable and testable.
- [ ] Persian RTL, keyboard, and narrow-screen behavior are covered where relevant.
- [ ] Access control and server-side validation are tested where relevant.
- [ ] Failure, retry, and duplicate-submission behavior are specified for side effects.
- [ ] Tests and Django system checks pass.

## Learning exercise
Name one Django concept this task teaches and the actual files/concepts the learner should trace. Include a short explanation in the PR, not a long tutorial in this issue.

## Out of scope
List adjacent behaviors, integrations, deployment, and data operations that this issue does not authorize.

## Open decisions
List unresolved product questions. Do not let the implementation agent silently decide business behavior.
