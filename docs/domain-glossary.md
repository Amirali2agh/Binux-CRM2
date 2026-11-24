# Product and domain glossary

The English term is used in code and documentation; the Persian label is the current UI wording. This glossary records owner-provided behavior. Anything listed as an open decision must not be guessed by an implementation agent.

## Customer record

A customer is a person or business managed by the internal team. Agreed attributes:

- Customer name
- Business type and business name
- Primary, secondary, and tertiary phone numbers (all optional)
- Customer status
- Customer type/source: phone call, Divar, in person, or other
- Address
- Notes/description

All fields are optional. A missing status defaults to `بدون تماس`. Phone numbers are stored as entered; format and uniqueness are not validated. Existing phone values remain primary numbers when optional second and third numbers are introduced. `ارسالی` is the exception to optional assignment: it cannot be saved without an active Django user assigned.

## Customer category

Each customer has exactly one category, independent of business type and customer source:

- `کسب‌وکار خرد` — Micro business
- `شرکت` — Company
- `مشتری CRM` — CRM customer
- `مشتری ERP` — ERP customer
- `نامشخص` — Uncategorized; default for existing and newly created records until a team member selects a category

The customer list provides an all-categories tab and one tab per category. Categories are not inferred from business type, source, or customer status.

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

Issue #25 selects a read-only Noghte call-history importer. The operator-run `sync_noghte_calls` command sends outbound-history GET requests only for non-empty phone values that occur on exactly one CRM record across all lifecycle states, and that one record is not archived or in Trash; completed customers remain eligible. Phone matching is exact and no normalization is performed. A number duplicated on an archived or trashed record is still ambiguous and is not sent to the provider.

- `answered` maps to call outcome `answered` and customer status `رد شده` (Rejected).
- `busy`, `failed`, `missed`, and `no_answer` map to call outcome `call_again` and customer status `تماس مجدد` (Call again).
- Unsupported statuses, inbound calls, unknown numbers, and ambiguous customer numbers are ignored.
- Provider call IDs make ingestion idempotent. Replays do not overwrite an edited call outcome; a manual customer-status change newer than the call event is preserved.
- The bearer token is read at runtime from a restricted file named by `NOGHTE_API_KEY_FILE`. The token, transcript, and provider summary are not logged or persisted. The exact customer phone number is sent in the provider query and copied to the linked `CallRecord.dialed_number`; command output contains aggregate counts, never phone numbers.
- This is not Click-to-call: it does not place calls. No scheduler is selected or configured; the command is run explicitly by an operator. Other external providers remain undecided.

## Open product decisions

- Phone format/normalization/uniqueness and address structure (all fields remain optional).
- Exact transition behavior for statuses other than the documented archive/trash restore flow.
- Which hosting scheduler will periodically run `process_customer_lifecycle` and how its failures will be monitored; no deployment target has been selected.
- Which additional external services will be integrated and which one owns each shared field.
