# Binux CRM — phase 1 (display only)

A Persian RTL Django learning project. Issues #1–#6 introduce the navigation shell and 17 distinct visual pages. All data is fictional. No login, database, save action, real customer, API integration, or deployment is included.

## Run locally

Use Python 3.11+ (with `venv` installed):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

If the host lacks `venv`, `uv venv --python 3.11 .venv` and `uv pip install --python .venv/bin/python -r requirements.txt` work too. Visit `http://127.0.0.1:8000/`. To run the tests: `.venv/bin/python manage.py test`. No migration command is necessary: there are no models or configured databases.

**Local preview only.** `config/settings.py` deliberately enables debug and uses an unsafe local secret. Never expose this server publicly or deploy these settings. Production needs separate security, authentication, storage, and deployment decisions.

## Follow one Django request (#1–#2)

1. The browser asks for `/internal/office-inventory/` (or `/` redirects there).
2. `config/urls.py` delegates to `crm/urls.py`; the named route `crm:office_inventory` calls `crm.views.display_page` with `page_key='office_inventory'`.
3. The view reads the fictional page definition from `crm/catalog.py` and passes `page`, `section`, `sections`, and `current_page` into `crm/page.html`. It does **not** query a database.
4. `crm/page.html` extends `crm/base.html`. The base draws the shared header and sidebar; the child fills `{% block content %}` with this page's preview. The sidebar generates links via `{% url %}` and marks the current route with `aria-current="page"`.
5. CSS styles the layout; JavaScript only toggles sidebar groups and mobile/collapsed navigation. If scripts are disabled, all links remain available.

**Exercise:** In `crm/catalog.py`, change a demo description, reload, and trace where its text appears. Add a new page definition and use `reverse('crm:<name>')` in the Django shell to inspect its named URL.

## Next learning steps (#3–#6)

- **Finance / view context:** Follow `receipts_payments` from a tuple in `crm/catalog.py` to `display_rows` in `crm/views.py` and finally a rendered table cell. Change only the fictional sample row; no model is needed.
- **Customers / loops and empty state:** Compare the table loop in `crm/page.html` with the empty follow-ups page. Try replacing a demo table's `rows` with an empty tuple and observe the fallback.
- **Contracts / template includes:** Both contract pages reuse `crm/partials/contract_preview.html` with different `contract_state` values. Edit the partial once and check both routes.
- **Servers and agents / test client:** Run `.venv/bin/python manage.py test crm`. `crm/tests.py` checks the 17 named GET routes, headings, demo markers, active navigation, 405 on POST, and fictional server content. Add an assertion for another page without depending on internal helper functions.

The next phase can add a real feature one issue at a time, with its model, permissions, validation, API/service adapter and tests designed **after** the workflow is specified. None of these placeholders should be treated as real operational state.

## Assets

The self-hosted Vazirmatn font is redistributed under the SIL Open Font License; see `static/crm/OFL.txt`. The icons are local inline SVGs. There are no runtime third-party requests.
