# Architecture and implementation map

## Current application (verified in the repository)

The current app is a server-rendered Django site. Customer records persist in the configured local SQLite database. Every CRM application page requires a Django team session, including display-only roadmap pages; the public login screen is the only application page available before sign-in. CRM access is enforced by explicit roles. The temporary role rollout promotes every account existing when migration `0010_elevate_existing_users_to_manager` is applied to `CRM Manager`; future accounts receive no role automatically, and marketer access remains pending the owner's decision. Django admin retains its separate authentication. Non-customer roadmap pages remain display-only and use clearly fictional examples.

A request follows this path:

1. `config/urls.py` includes the CRM URL configuration.
2. `crm/urls.py` defines named CRM routes; `login_required` protects the application views, while the login and logout routes remain separately available.
3. `crm/views.py` resolves pages or filters customer records; `crm/forms.py` validates customer input.
4. `crm/models.py` stores customer fields, assignment, lifecycle timestamps, and database constraints; `crm/catalog.py` holds the remaining static demo content and shared menu.
5. `templates/crm/base.html` renders the shared shell; customer templates render forms and filtered lists; `static/crm/app.css` and `static/crm/app.js` provide styling and navigation behavior.
6. `crm/tests.py` exercises display routes, authentication, form validation, persistence, and lifecycle behavior.

This map distinguishes live customer records from the remaining fictional `catalog.py` demo rows; demo rows are never customer business data.

## Product roadmap

The menu is an information architecture map. The first real workflow is customer management, including its customer list, follow-up view, assigned work, completed customers, archive, and trash lifecycle. Other menu areas remain unimplemented roadmap items until an issue defines their business rules.

Issue #25 selects one narrow integration: Noghtefone call ingestion. Signed webhooks enter through `crm:noghtefone_webhook`. Provider HTTP, HMAC verification, and provisional payload parsing stay in `crm/integrations/noghtefone/` and `crm/integrations/noghte.py`. `crm/call_ingestion.py` associates a provider-neutral outcome with a customer. `sync_noghte_calls` is the operator-run outbound backfill. Credentials come from `NOGHTE_WEBHOOK_SECRET` / `NOGHTE_WEBHOOK_SECRET_PREVIOUS` and the file named by `NOGHTE_API_KEY_FILE`. No scheduler is configured. The flow does not place calls or store transcripts. Before adding any further provider, document the user workflow, system of record, fields exchanged, authentication/secret handling, retries, duplicate handling, and failure behavior in a scoped issue.

## Intended customer-domain boundaries

The agreed customer attributes and lifecycle are recorded in `domain-glossary.md`. The customer domain now follows these boundaries:

- Keep customer identity and lifecycle state in Django's domain/model layer, not in template-only logic.
- Use named routes and ordinary Django forms/views unless the issue establishes a justified API requirement.
- Enforce required assignment when status is `ارسالی` on the server and in a database constraint, not only by coloring a browser field red.
- Keep active, completed, archived, and trash views distinct. A customer must not appear in the active list after it leaves that lifecycle state.
- Make delayed transitions and retention rules idempotent, timestamp-based, testable, and recoverable where specified.
- Do not introduce extra models, roles, statuses, integrations, or automatic side effects without an issue or an explicit product decision.

These boundaries apply to the implemented customer workflow and constrain future changes.

## Learning path

Use the real feature to teach Django incrementally: route and view, form validation, model and migration, template rendering, tests, then lifecycle handling. Explain each layer using the actual changed files and a short request-to-response or state-transition trace. Avoid teaching with invented helper abstractions that the project does not use.
