# Binux CRM

A Persian RTL, learning-first Django CRM for internal customer and work management. The customer workflow now stores records in SQLite and requires team login; the other menu destinations remain display-only with fictional data. See `AGENTS.md`, `PRODUCT.md`, and `docs/` for project rules, architecture, setup, and the agreed customer lifecycle.

## Run locally

Use Python 3.11+ (with `venv` installed):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

If Python's `venv` module is unavailable, use `uv venv --python 3.11 .venv` and `uv pip install --python .venv/bin/python -r requirements.txt`. Before first use, initialize the database with `.venv/bin/python manage.py migrate`, create an administrator with `.venv/bin/python manage.py createsuperuser`, then visit `/admin/` to create team users. Run `.venv/bin/python manage.py test` for the suite. See `docs/setup.md` for lifecycle maintenance and security boundaries.

For optional desktop/mobile keyboard and no-JavaScript browser checks, install `playwright` in the local environment and run `.venv/bin/python scripts/browser_smoke.py` while the Django server is running. Point `CHROME_PATH` at an installed Chrome/Chromium binary if it is not at `/usr/bin/google-chrome`; use `CRM_BASE_URL` if the server is not on port 8000. This browser dependency is deliberately not required to serve the app.

**Local preview only.** `config/settings.py` deliberately enables debug and uses an unsafe local secret. Never expose this server publicly or deploy these settings. Production needs separate security, authentication, storage, and deployment decisions.

## Follow one Django request (#1–#2)

1. The browser asks for `/internal/office-inventory/` (or `/` redirects there).
2. `config/urls.py` delegates to `crm/urls.py`; the named route `crm:office_inventory` calls `crm.views.display_page` with `page_key='office_inventory'`.
3. The view reads the fictional page definition from `crm/catalog.py` and passes `page`, `section`, `sections`, and `current_page` into `crm/page.html`. It does **not** query a database.
4. `crm/page.html` extends `crm/base.html`. The base draws the shared header and sidebar; the child fills `{% block content %}` with this page's preview. The sidebar generates links via `{% url %}` and marks the current route with `aria-current="page"`.
5. CSS styles the layout; JavaScript only toggles sidebar groups and mobile/collapsed navigation. If scripts are disabled, all links remain available.

**Exercise:** In `crm/catalog.py`, change a demo description, reload, and trace where its text appears. Add a new page definition and use `reverse('crm:<name>')` in the Django shell to inspect its named URL.

## Customer workflow request path (#4)

1. The user signs in with a Django account created by an administrator; customer routes use `login_required`.
2. `crm/urls.py` maps the customer list/form to `crm/views.py`; `CustomerForm` validates fields and requires an assignee when status is `ارسالی`.
3. `crm/models.py` persists the customer and status timestamps in SQLite; the database constraint also rejects `ارسالی` without an assignee.
4. Customer list, Follow-up, Tasks, Completed, Archive, and Trash views filter separate lifecycle states and render the customer templates under `templates/crm/`.
5. `process_customer_lifecycle` applies rejected-customer archive transitions and retention purges; production must schedule it before using real customer data.

**Learning exercise:** Trace a blank form submission through `crm/urls.py`, `CustomerForm`, `Customer.save()`, and the rendered list. Compare the validation error for an unassigned `ارسالی` customer to the database constraint.

## Remaining roadmap learning steps (#3, #5–#6)

- **Finance / view context:** Follow `receipts_payments` from a tuple in `crm/catalog.py` to `display_rows` in `crm/views.py` and finally a rendered table cell. Change only the fictional sample row; no model is needed.
- **Contracts / template includes:** Both contract pages reuse `crm/partials/contract_preview.html` with different `contract_state` values. Edit the partial once and check both routes.
- **Servers and agents / test client:** Run `.venv/bin/python manage.py test crm`. Tests cover the display pages plus authenticated customer behavior, validation, and lifecycle boundaries.

The remaining menu groups are roadmap placeholders. Do not treat demo samples as real operational state or add an external integration until a provider and behavior are explicitly selected.

## Project guidance

- `AGENTS.md` — workflow, branch/PR rules, safe data handling, educational handoff, and verification requirements.
- `docs/architecture.md` — current request path and future customer-domain boundaries.
- `docs/setup.md` — environment, run, test, and migration guidance.
- `docs/domain-glossary.md` — approved product terms, customer lifecycle, and open decisions.
- `.github/ISSUE_TEMPLATE/feature_request.md` — scoped, testable feature and learning issue template.

## Assets

The self-hosted Vazirmatn font is redistributed under the SIL Open Font License; see `static/crm/OFL.txt`. The icons are local inline SVGs. There are no runtime third-party requests.
