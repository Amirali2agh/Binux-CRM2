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

## Database and migrations

The checked-in display-only app has no configured database or models, so it needs no migrations. When an issue adds persistent customer data, first inspect the settings and issue scope, then create and test migrations using Django's standard `makemigrations` and `migrate` commands. Never apply migrations to a live system as part of a local feature PR.

## Troubleshooting

- If the browser cannot load the page, confirm the server is running at `127.0.0.1:8000` and use the exact `CRM_BASE_URL` value required by the smoke script.
- If the virtual environment is missing, recreate `.venv`; do not install project dependencies globally.
- If a test fails, reproduce it with the smallest relevant Django test command, inspect the changed route/view/template and report failures rather than weakening assertions without a product reason.
