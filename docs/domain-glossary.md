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

Issue #25 connects CRM call history to Noghtefone. Signed webhooks are the primary ingestion path. `sync_noghte_calls` is an operator-run, read-only outbound backfill. Neither path places calls. No scheduler is configured. Details and open provider questions are in `docs/noghtefone-integration.md`.

Iranian numbers `0912…`, `+98912…`, `98912…`, and `912…` are the same subscriber. A call is associated only when that key belongs to exactly one CRM customer and that customer is not archived or in Trash. Unknown numbers are stored on a delivery row and are not attached to a customer. A number shared with any other record, including an archived or trashed one, is ambiguous and is not attached.

- `call.answered`, and provider status `answered`, map to call outcome `answered` and customer status `رد شده` (Rejected).
- `busy`, `failed`, `missed`, and `no_answer` map to call outcome `call_again` and customer status `تماس مجدد` (Call again).
- Any other non-empty status, and a call event with no status, is outcome `unknown` (`نامشخص / پشتیبانی‌نشده`). It is recorded and does not change the customer.
- Webhook idempotency uses `X-Noghte-Delivery` and the event id. The same provider call id updates one call record. An operator save locks the outcome so later provider events do not overwrite it. A customer-status change newer than the call time is preserved.
- The webhook signing secret is read from `NOGHTE_WEBHOOK_SECRET`, with `NOGHTE_WEBHOOK_SECRET_PREVIOUS` during rotation. The backfill bearer token is read from the restricted file named by `NOGHTE_API_KEY_FILE`. Secrets are not logged or committed. Command output contains aggregate counts, never phone numbers.
- Inbound webhook calls can match the caller. The backfill requests outbound history only. Other external providers remain undecided.

## Open product decisions

- Phone uniqueness and address structure (all fields remain optional). Noghtefone matching normalizes Iranian number forms; other uniqueness rules are still open. The exact provider payload fields are listed in `docs/noghtefone-integration.md`.
- Exact transition behavior for statuses other than the documented archive/trash restore flow.
- Which hosting scheduler will periodically run `process_customer_lifecycle` and how its failures will be monitored; no deployment target has been selected.
- Which additional external services will be integrated and which one owns each shared field.
