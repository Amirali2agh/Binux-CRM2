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

Open `http://127.0.0.1:8000/`. The CRM login screen is shown first; after successful team sign-in the requested page opens. The current version is a local display-only demo, not a production deployment. Do not expose it publicly: its settings enable debug mode and use an unsafe local fallback secret.

## Local Docker development

Docker support is for local development only. It uses Django's development server, the existing local-only fallback secret when `DJANGO_SECRET_KEY` is not set, and SQLite; it is not a production setup. The lifecycle management command still needs a separately selected scheduler (tracked in issue #10), which this setup does not configure or run.

From the repository root, build the image and initialize the SQLite database in the Compose named volume:

```bash
docker compose build
docker compose run --rm web python manage.py migrate
```

Optionally create an administrator for `/admin/`:

```bash
docker compose run --rm web python manage.py createsuperuser
```

Start the development server and open `http://localhost:8000/`:

```bash
docker compose up
```

The project directory is bind-mounted at `/app`, so local code edits are visible in the container. SQLite is stored at `/data/db.sqlite3` in the named `crm_data` volume and survives ordinary container recreation. Stop with `Ctrl+C`, then run:

```bash
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete the local database volume. Compose reads `DJANGO_DEBUG` and `DJANGO_SECRET_KEY` from the environment (or a root `.env` file); `.env` is ignored by Git and Docker. The fallback secret is only for local development; never expose this server publicly.

Run the Django tests in the container with:

```bash
docker compose run --rm web python manage.py test
```

Compare with the regular local test command in the Verification section below. The default SQLite location remains `db.sqlite3` beside the code when `DJANGO_DB_PATH` is not set.

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
