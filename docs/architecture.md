# Architecture and implementation map

## Current application (verified in the repository)

The current app is a server-rendered Django site. It has no configured database, models, authentication, or persistent CRM records. Its 17 pages are display-only and use fictional examples.

A request follows this path:

1. `config/urls.py` includes the CRM URL configuration.
2. `crm/urls.py` defines named routes from the page catalog.
3. `crm/views.py` resolves a page and prepares presentation context.
4. `crm/catalog.py` holds the menu and current static demo content.
5. `templates/crm/base.html` renders the shared shell; `templates/crm/page.html` renders the selected page; reusable fragments live under `templates/crm/partials/`.
6. `static/crm/app.css` and `static/crm/app.js` provide styling and navigation behavior.
7. `crm/tests.py` exercises routes and display-only guarantees.

This map describes the checked-in display-only implementation. Do not treat `catalog.py` demo rows as business data.

## Product roadmap

The menu is an information architecture map. The first real workflow is customer management, including its customer list, follow-up view, assigned work, completed customers, archive, and trash lifecycle. Other menu areas remain unimplemented roadmap items until an issue defines their business rules.

Future integrations are intentionally undecided. Before adding one, document the user workflow, system of record, fields exchanged, authentication/secret handling, retries, duplicate handling, and failure behavior in a scoped issue. Implement provider-specific details behind a narrow adapter; keep the customer domain independent of any one external service.

## Intended customer-domain boundaries

The agreed customer attributes and lifecycle are recorded in `domain-glossary.md`. When the first persistent workflow is designed:

- Keep customer identity and lifecycle state in Django's domain/model layer, not in template-only logic.
- Use named routes and ordinary Django forms/views unless the issue establishes a justified API requirement.
- Enforce required assignment when status is `Sent` on the server, not only by coloring a browser field red.
- Keep active, completed, archived, and trash views distinct. A customer must not appear in the active list after it leaves that lifecycle state.
- Make delayed transitions and retention rules idempotent, timestamp-based, testable, and recoverable where specified.
- Do not introduce extra models, roles, statuses, integrations, or automatic side effects without an issue or an explicit product decision.

These are architecture constraints for future work, not claims that the features already exist.

## Learning path

Use the real feature to teach Django incrementally: route and view, form validation, model and migration, template rendering, tests, then lifecycle handling. Explain each layer using the actual changed files and a short request-to-response or state-transition trace. Avoid teaching with invented helper abstractions that the project does not use.
