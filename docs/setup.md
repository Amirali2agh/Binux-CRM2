# Local development and checks

## Requirements

- Python 3.11 or newer
- Git
- `venv` support in Python

The project currently requires Django 5.2.x (see `requirements.txt`).

## Create an isolated environment

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

If Python's `venv` module is unavailable but `uv` is installed:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

## Run the current application

```bash
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/`. The current version is a local display-only demo, not a production deployment. Do not expose it publicly: its settings enable debug mode and use an unsafe local fallback secret.

## Verification

Run these from the repository root:

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test
```

Optional browser smoke test (requires Playwright installed in the environment and the server already running):

```bash
.venv/bin/python scripts/browser_smoke.py
```

Set `CHROME_PATH` if Chromium is not at `/usr/bin/google-chrome`, or `CRM_BASE_URL` if the server uses a different local URL. Browser automation is optional; it is not required to run Django tests.

## Database, accounts, and lifecycle maintenance

The app uses a local SQLite database at `db.sqlite3` by default. After installing dependencies, initialize it and create the first administrator:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
```

Sign in at `/admin/` and create active team users there. Team users share the same customer access level; there is no public sign-up or role hierarchy. Do not use the local fallback secret or debug settings in a public deployment.

The `process_customer_lifecycle` management command archives rejected customers at the two-hour boundary and permanently removes archived/trash records after their retention periods. A deployment must run this command periodically (for example, every five minutes) for those automatic transitions to execute. No production scheduler or deployment is configured by this repository; choose and monitor one before using real customer data. The command is transactional and safe to retry.

Migrations are checked in under `crm/migrations/`. Use Django's standard `makemigrations` and `migrate` commands when the model changes. Never apply migrations to a live system as part of a local feature PR.

## Troubleshooting

- If the browser cannot load the page, confirm the server is running at `127.0.0.1:8000` and use the exact `CRM_BASE_URL` value required by the smoke script.
- If the virtual environment is missing, recreate `.venv`; do not install project dependencies globally.
- If a test fails, reproduce it with the smallest relevant Django test command, inspect the changed route/view/template and report failures rather than weakening assertions without a product reason.
