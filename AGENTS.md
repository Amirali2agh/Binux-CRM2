# Binux CRM contributor and coding-agent guide

## Mission
Build an internal, learning-first CRM for managing customers and work. The primary product focus is customer management. The interface is Persian and right-to-left; repository documentation, code identifiers, issues, and pull requests are in English. Teach through small, reviewable changes: trace the existing flow, make one focused change, test it, and explain briefly what changed and why.

## Product direction and current state
- The Django project currently contains a display-only shell and 17 menu destinations. Read `README.md`, `PRODUCT.md`, and `docs/architecture.md` before changing it.
- The menu is a roadmap, not proof that a workflow exists. Do not imply that a demo page, fictional record, server status, contract, finance item, or agent is real.
- The first real workflow is customer management. Its agreed fields and lifecycle are in `docs/domain-glossary.md`; future external integrations are not yet selected.
- Other menu groups remain roadmap items until an issue defines their actual behavior. Do not implement imagined finance, contract, server, or agent operations.

## Before implementation
1. Read the relevant issue and inspect its state, the target page, neighboring code, and current tests.
2. Check the open pull requests for overlapping work. Do not duplicate work already delivered or in flight.
3. Treat the issue's acceptance criteria as the scope. If a requirement is missing or conflicts with product docs, stop and report the exact question; do not silently invent business rules.
4. For real customer data, identify the data lifecycle, access control, validation, and failure behavior before coding. Never copy production/customer data into tests, logs, fixtures, or screenshots.

## Implementation rules
- Work on a task branch and open a pull request. Never commit or push to `main` or the repository's default branch, and never merge your own PR.
- Keep each change focused on its issue. Do not add external integrations, deployment, or unrelated features without an issue.
- Preserve Persian RTL behavior, accessible keyboard navigation, responsive layouts, and existing route/template conventions.
- Use Django's normal separation: URL -> view -> model/service as needed -> template. Keep business rules out of templates. Add migrations only when required and never rewrite an applied migration.
- Do not introduce credentials, real customer data, or secrets into the repository. Do not run destructive commands against any real data.
- For lifecycle automation (archive, trash, retention, permanent deletion), use explicit timestamps and test boundary cases, duplicate execution, restoration, and failure/retry behavior. Permanent deletion must match the documented retention rule and must never be broadened by inference.
- Treat future integrations as adapters behind narrow interfaces. No provider, API, or external side effect is authorized merely because the product may integrate later.

## Learning and communication
- Keep code and committed documentation in English; keep conversation with the owner in Persian.
- In each implementation PR, add a short `Learning note`: the Django concept used, where it appears in this repository, and one concise explanation of the request/data flow.
- Prefer explaining the relevant code path over adding comments that merely restate code. Ask only for product decisions that cannot be recovered from the issue or repository; decide and document routine implementation details.

## Verification and completion
- Run the repository's documented checks from `docs/setup.md`; add focused tests for every changed behavior.
- Do not claim a test, browser check, migration, or manual verification that was not actually run. Report exact commands and outcomes.
- Before opening a PR, review the diff for scope, secrets, customer data, generated files, and migration safety. The PR must state what changed, why, tests run, learning note, and remaining open decisions.
- A PR is not a deployment. Do not deploy, alter live data, or contact customers.
