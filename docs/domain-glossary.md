# Product and domain glossary

The English term is used in code and documentation; the Persian label is the current UI wording. This glossary records owner-provided behavior. Anything listed as an open decision must not be guessed by an implementation agent.

## Customer record

A customer is a person or business managed by the internal team. Agreed attributes:

- Customer name
- Business type and business name
- Phone number
- Customer status
- Customer type/source: phone call, Divar, in person, or other
- Address
- Notes/description

Field requiredness, phone normalization/uniqueness, and address structure have not yet been specified.

## Customer statuses

Use the exact product labels in the Persian UI. English code-facing labels below are descriptive mappings, not a mandate to change the UI wording.

- `بدون تماس` — No contact
- `رد شده` — Rejected
- `پیگیری` — Follow-up
- `ارسالی` — Sent: something must be sent to the customer, or something is expected from them. This status requires assignment to a team member. If no assignee is selected, the assignment field must be visibly marked as an error (red), and the record must not be accepted as a valid `ارسالی` state. The customer also appears in the Follow-up view.
- `تماس مجدد` — Call again
- `انجام شده` — Completed: the customer appears in a separate completed-customers view.

Allowed transitions, whether a reason is required, and what happens when a completed/rejected customer changes status again remain open decisions unless specified by an issue.

## Customer type/source

- `تماس تلفنی` — Phone call
- `دیوار` — Divar
- `حضوری` — In person
- `سایر` — Other

## Assignment and task view

A customer can be assigned/referred to one person. The Tasks view lists customers that have an assignee. The owner has not yet specified the assignee directory/source, whether assignment is mandatory for statuses other than `ارسالی`, task dates/reminders, or whether a separate task entity is needed. Do not invent these behaviors.

## Follow-up view

Customers with status `پیگیری` appear in the Follow-up section. Customers with status `ارسالی` also appear there. This view is a filtered presentation of customer work unless a later issue defines separate follow-up records.

## Completed customers

Customers explicitly set to `انجام شده` appear in a separate completed-customers view. This is not the archive and is not the trash.

## Archive

The archive is separate from trash. It contains manually archived customers and rejected customers automatically moved there two hours after their status changes to `رد شده`. Both kinds appear in the same archive list; no separate archive category is required. A customer in the archive can be restored. Archived records are retained for one month, then permanently deleted.

## Trash

Deleting a customer moves it to trash rather than deleting it immediately. It remains recoverable from trash for 10 days, then is permanently deleted. Restoring from trash is allowed during the retention period. Trash is not the archive.

## Integrations

External services are planned for the future but none have been selected. Do not add provider-specific code, credentials, network calls, or synchronization assumptions until a dedicated issue names the service and behavior.

## Open product decisions

- Which customer fields are required; phone format, uniqueness, and validation.
- How users/team members are created and selected as assignees.
- Exact transition rules when a customer leaves `رد شده`, `ارسالی`, `پیگیری`, or `انجام شده`.
- Whether assignment is required for any status other than `ارسالی`.
- Whether archival/trash retention has a user-visible countdown and how a retention job is scheduled and monitored.
- Which external services will be integrated and which one owns each shared field.
