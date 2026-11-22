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

All fields are optional. A missing status defaults to `بدون تماس`. Phone format and uniqueness are not validated. `ارسالی` is the exception to optional assignment: it cannot be saved without an active Django user assigned.

## Customer statuses

Use the exact product labels in the Persian UI. English code-facing labels below are descriptive mappings, not a mandate to change the UI wording.

- `بدون تماس` — No contact
- `رد شده` — Rejected
- `پیگیری` — Follow-up
- `ارسالی` — Sent: something must be sent to the customer, or something is expected from them. This status requires assignment to a team member. If no assignee is selected, the assignment field must be visibly marked as an error (red), and the record must not be accepted as a valid `ارسالی` state. The customer also appears in the Follow-up view.
- `تماس مجدد` — Call again
- `انجام شده` — Completed: the customer appears in a separate completed-customers view.

Changing status updates the status-change timestamp. Restoring from either Archive or Trash sets status to `پیگیری` and stores the restoration origin so the Follow-up view can say where the customer returned from. Other transition-specific behavior remains open unless specified by an issue.

## Customer type/source

- `تماس تلفنی` — Phone call
- `دیوار` — Divar
- `حضوری` — In person
- `سایر` — Other

## Assignment and task view

A customer can be assigned/referred to one active Django user. The Tasks view lists assigned customers that are not archived or in Trash, including completed customers if they remain assigned. Team accounts are provisioned through Django administration; there is no public self-sign-up or role hierarchy. Task dates/reminders and a separate task entity are not part of this workflow.

## Follow-up view

Customers with status `پیگیری` appear in the Follow-up section. Customers with status `ارسالی` also appear there. This view is a filtered presentation of customer work unless a later issue defines separate follow-up records.

## Completed customers

Customers explicitly set to `انجام شده` appear in a separate completed-customers view. This is not the archive and is not the trash.

## Archive

The archive is separate from trash. It contains manually archived customers and rejected customers automatically moved there two elapsed hours after their status-change timestamp. Both kinds appear in the same archive list; no separate archive category is required. A customer in the archive can be restored to Follow-up before expiry, with the origin recorded. Archived records are retained for 30 elapsed days, then permanently deleted.

## Trash

Deleting a customer moves it to trash rather than deleting it immediately. It remains recoverable for 10 elapsed days after deletion, then is permanently deleted. Restoring from trash is allowed before expiry and sets status to Follow-up with the origin marked as Trash. Trash is not the archive.

## Integrations

External services are planned for the future but none have been selected. Do not add provider-specific code, credentials, network calls, or synchronization assumptions until a dedicated issue names the service and behavior.

## Open product decisions

- Phone format/normalization/uniqueness and address structure (all fields remain optional).
- Exact transition behavior for statuses other than the documented archive/trash restore flow.
- Which hosting scheduler will periodically run `process_customer_lifecycle` and how its failures will be monitored; no deployment target has been selected.
- Which external services will be integrated and which one owns each shared field.
