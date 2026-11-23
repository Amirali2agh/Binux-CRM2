# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
Django (Python) with server-rendered HTML templates, CSS, and plain JavaScript for sidebar navigation. This stack was explicitly requested before the issue planning.

## Users
The initial audience is the internal team. Django's built-in authentication and administration provision team accounts with the same access level; no role hierarchy or public self-sign-up is requested.

## Product Purpose
An educational, internal CRM for managing customers and assigned work. The application provides the first persistent, authenticated customer workflow; other menu destinations remain a roadmap, not a list of implemented features.

## Capabilities and Constraints
The application includes the original 17 destinations from issues #1–#6 plus four customer workflow views. The customer list, follow-up view, assignment, completed view, archive, and trash are backed by authenticated persistent records. The lifecycle command is implemented but still needs an environment scheduler; no retention automation runs until deployment configures it. Finance, contract, internal operations, and server/agent pages remain roadmap placeholders. No external integration has been selected. Persian RTL interface; English repository artifacts and a concise educational explanation in each implementation PR.

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
