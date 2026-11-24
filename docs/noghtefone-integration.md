# Noghtefone call ingestion

Webhook delivery is the primary way call activity enters the CRM. The operator-run `sync_noghte_calls` command remains a read-only backfill against `GET /calls`. Neither path places calls. No scheduler is configured.

The provider adapter lives in `crm/integrations/noghtefone/` (signatures, provisional payload parsing, event-to-outcome mapping) and `crm/integrations/noghte.py` (the backfill HTTP client). Customer association lives in `crm/call_ingestion.py` and only sees a provider-neutral outcome, a match key, and ids.

## Secrets

Set these in the process environment. Do not commit them, pass them as command arguments, or write them into logs.

| Variable | Purpose |
| --- | --- |
| `NOGHTE_WEBHOOK_SECRET` | Current webhook signing secret. Required for the webhook. If it is empty, every delivery is rejected. |
| `NOGHTE_WEBHOOK_SECRET_PREVIOUS` | Previous signing secret, used only during rotation. Optional. |
| `NOGHTE_WEBHOOK_TOLERANCE_SECONDS` | Allowed clock skew for `t` in the signature. Default `300` (five minutes, as documented by Noghtefone). |
| `NOGHTE_API_KEY_FILE` | Path to a mode-`0600` file containing the `np_live_…` bearer token. Used only by the backfill command. |

Rotation: put the new signing secret in `NOGHTE_WEBHOOK_SECRET` and the old one in `NOGHTE_WEBHOOK_SECRET_PREVIOUS`. Keep the previous secret until in-flight retries finish. Noghtefone retries for up to about two hours, so leave the previous secret in place for at least that long, then unset it. The API key file is replaced on disk; restart or rerun the command so it reads the new file. Do not record either secret in the issue tracker.

## Webhook URL and events

In Noghtefone, under Integrations → Webhooks, create a webhook that POSTs to:

```text
https://<your-crm-host>/integrations/noghtefone/webhook/
```

The path is named `crm:noghtefone_webhook`. It is not behind the team login form. Noghtefone authenticates with `X-Noghte-Signature` (`t=<unix>,v1=<hex HMAC-SHA256>` over `t + "." + raw body`). The CRM compares the hex digest with `hmac.compare_digest` and rejects timestamps outside the tolerance.

Subscribe to the call events the CRM understands:

- `call.started`
- `call.answered`
- `call.ended`
- `call_result.created`
- `voicemail.created`

Other documented events (`recording.ready`, `transcript.ready`, `insight.ready`, `ai_agent.conversation_ended`, `callback.requested`, `contact.created`) are stored and ignored. They do not create a call or change a customer. A 2xx is returned after the delivery row is stored so Noghtefone does not retry a permanently unusable body. A signature or timestamp failure returns 401 and is not stored. A database error before commit returns 503 so Noghtefone retries (it retries non-2xx up to six times, from about 10 seconds to two hours, then disables the webhook after 100 consecutive failures).

## What gets associated

A call is linked to a customer only when the normalized number belongs to exactly one customer in the whole CRM, and that customer is not archived or in Trash. These Iranian forms are the same number: `09121234567`, `+989121234567`, `989121234567`, and `9121234567` (Persian digits are accepted). Inbound events use the caller fields; other events use the callee fields.

| Situation | Stored delivery | Call history | Customer status |
| --- | --- | --- | --- |
| One active customer | `matched` | One `CallRecord` per call id | See outcome mapping |
| No customer | `unmatched` | None | Unchanged |
| Two or more customers, including archived or trashed | `ambiguous` | None | Unchanged |
| Only an archived or trashed customer | `inactive` | None | Unchanged |
| Same `X-Noghte-Delivery` or same event `id` again | No second row | Unchanged | Unchanged |

`call.answered` means outcome `answered` even when the provisional status field is missing. `answered` sets the customer to `rejected`. `busy`, `failed`, `missed`, and `no_answer` mean `call_again` and set the customer to `call_again`. Any other non-empty status, and call events with no status (`call.started`, `call.ended` without a status, `voicemail.created` without a status), are stored as outcome `unknown` (`نامشخص / پشتیبانی‌نشده`). Unknown does not change the customer. A later specific outcome may replace `unknown`, or replace another specific outcome, until an operator saves the outcome on the customer page. That save locks the outcome; later provider events do not overwrite it. A customer status change newer than the call time is also left alone.

Deliveries are visible in Django admin under Call events (read-only), including failures and unknown numbers. Admin does not store the raw body or any secret. Logs include the delivery id and disposition only.

## Backfill command

```bash
NOGHTE_API_KEY_FILE=/secure/path/to/api-key .venv/bin/python manage.py sync_noghte_calls --since YYYY-MM-DD
```

The command queries outbound history only for numbers that belong to exactly one non-archived, non-trashed customer, using the same normalization as webhooks. It sends the phone string stored on the customer as the `number` query parameter. Rows whose number does not match, inbound rows, and rows with no status are skipped. An unrecognized status is imported as `unknown` and does not change the customer. Provider call ids keep retries idempotent. Output is aggregate counts and does not include phone numbers or the API key.

The documented tests mock HTTP. Do not point this command at a live CRM database as part of a feature check, and do not call the real Noghtefone API from tests.

## Provisional payload fields

Noghtefone documents the webhook envelope `{id, event, created_at, data}` and the `GET /calls` URL. It does not document the call object. The parser assumes these keys inside `data`, in order:

- call id: `uuid`, `call_uuid`, `id`
- callee: `to`, `destination`, `number`, `phone`
- caller: `from`, `caller`, `source`
- status: `status`, `result`
- time: `started_at`, `created_at`, then the envelope `created_at`
- direction: `direction`

The backfill client additionally assumes each row has `id`, `direction`, `to`, `status`, `started_at`, and `answered_at` or `ended_at`, and that list pages use `data`, `current_page`, and `last_page`. Those names are isolated in the adapter so they can be corrected without rewriting customer rules.

## Open questions for the owner

1. What are the exact call-object fields on webhook `data` and on `GET /calls` rows (id, phone, direction, status, timestamps)?
2. What status/result values can appear, besides the ones this importer already maps (`answered`, `busy`, `failed`, `missed`, `no_answer`)?
3. Which phone format does Noghtefone send in payloads, and which format does `GET /calls?number=` expect?
4. Is the webhook signing secret per webhook or account-wide?
5. Do retries reuse `X-Noghte-Delivery` and the body `id`? The CRM treats either value as an idempotency key.
6. Should inbound calls be linked to the caller (current webhook behavior) or ignored the way the outbound-only backfill ignores them?
7. Should `voicemail.created` imply an unanswered outcome, or stay `unknown` until a status field is confirmed (current behavior)?
8. Confirm that an answered call should still move the customer to `rejected`, which is the mapping already recorded for the importer.
