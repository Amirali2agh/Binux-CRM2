# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
Django (Python) with server-rendered HTML templates, CSS, and plain JavaScript for sidebar navigation. This stack was explicitly requested before the issue planning.

## Users
The initial audience is the internal team. The first release uses a simple login and the same access level for team members; detailed account provisioning remains open. No role hierarchy has been requested.

## Product Purpose
An educational, internal CRM for managing customers and assigned work. The current application is a display-only visual shell; the first real workflow is customer management, to be built incrementally while teaching Django through small, inspectable changes. The menu is a roadmap, not a list of features already implemented.

## Capabilities and Constraints
The checked-in application currently has five menu groups and 17 destinations from issues #1–#6; these remain display-only and mark fictional examples as demos. The first real workflow is customer management with persistent records, simple login, and the owner-agreed fields/lifecycle in `docs/domain-glossary.md`. Other menu groups remain roadmap placeholders. No external integration has been selected. Persian RTL interface; English repository artifacts and a concise educational explanation in each implementation PR.

## Brand Commitments
The name is Binux CRM. The user provided a visual reference for a dark, right-aligned RTL sidebar with grouped navigation, icons, profile/search placeholders, and a collapse control; its original menu copy, branding, and personal data are not to be copied.

## Evidence on Hand
The five groups and exact Persian submenu labels are specified in issues #1–#6. The owner specified the customer attributes and lifecycle recorded in `docs/domain-glossary.md`; no customer records have been supplied. No finance, contract, agent, server, or integration behavior has been specified. Any example data must remain explicitly fictional.

## Product Principles
- Learn through small, inspectable Django routes, views, templates, and tests.
- Make the page destination obvious without implying a functioning business workflow.
- Preserve room for future integration without building it prematurely.
- Keep customer data lifecycle and assignment rules explicit, testable, and separate from display templates.
- Explain each implementation briefly so the owner can learn the Django concepts in the real code path.
