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

## Phone call history sync

Issue #25 adds a manual, read-only import from Noghte; it does not place calls or run on a schedule. The command queries outbound call history only for exact phone values that occur on exactly one CRM record across all lifecycle states, with that record neither archived nor in Trash. Completed records remain eligible. A number duplicated on any record (including archived or trashed records), an unknown number, inbound call, or unsupported provider status is skipped. Provider call IDs make retries safe; a later manual customer-status change and manually edited call outcome are not overwritten.

Set `NOGHTE_API_KEY_FILE` in the command's environment to the path of a permission-restricted file containing the bearer token. On POSIX, the file must not be accessible by group or other users (for example, mode `0600`); the client rejects broader permissions. The command reads the file at runtime. Do not pass the token on the command line, commit it, or print it. The command does not fetch or store call transcripts or provider summaries, and its output contains aggregate counts only.

Run an explicit date window with:

```bash
NOGHTE_API_KEY_FILE=/secure/path/to/api-key .venv/bin/python manage.py sync_noghte_calls --since YYYY-MM-DD
```

The command uses the provider's read-only `GET /api/public/v1/calls` endpoint. Transient network errors and HTTP 429, 500, 502, 503, and 504 responses are retried up to three attempts; other HTTP errors or invalid responses exit non-zero. Rerun with the same `--since` date after correcting the cause; already imported call IDs are skipped. The documented CI tests mock HTTP and do not use the provider credential or contact Noghte. Never run this command against a live CRM database as part of a feature check; no production server or scheduler is configured here.

## Troubleshooting

- If the browser cannot load the page, confirm the server is running at `127.0.0.1:8000` and use the exact `CRM_BASE_URL` value required by the smoke script.
- If the virtual environment is missing, recreate `.venv`; do not install project dependencies globally.
- If a test fails, reproduce it with the smallest relevant Django test command, inspect the changed route/view/template and report failures rather than weakening assertions without a product reason.
