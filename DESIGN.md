---
name: Binux CRM
description: A learning-first Persian RTL CRM workspace, initially display-only.
colors:
  sidebar-navy: "#17223a"
  active-blue: "#355c98"
  focus-blue: "#66b6ff"
  work-ground: "#f4f6fa"
  card-white: "#ffffff"
  main-ink: "#202b41"
  secondary-ink: "#657389"
typography:
  headline:
    fontFamily: "Vazirmatn, Tahoma, sans-serif"
    fontSize: "clamp(26px, 2.8vw, 38px)"
    fontWeight: 750
    lineHeight: 1.5
  body:
    fontFamily: "Vazirmatn, Tahoma, sans-serif"
    fontSize: "13px"
    lineHeight: 2
rounded:
  nav: "8px"
  surface: "14px"
spacing:
  tight: "8px"
  regular: "16px"
  section: "24px"
components:
  nav-active:
    backgroundColor: "{colors.active-blue}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.nav}"
    padding: "6px 10px"
  surface:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.main-ink}"
    rounded: "{rounded.surface}"
---

# Binux CRM visual system — phase 1

## Overview
A practical Persian RTL workspace. The supplied screenshot is authority for the dark right-hand grouped sidebar, not for its wording, brand, personal details, or business data. The reading pane stays calm so real future workflows can take priority over decoration.

## Colors
The navy rail (`#17223a`) frames the app. The active link (`#355c98`) has a filled state, while focus (`#66b6ff`) remains visible in both light and dark areas. The work canvas (`#f4f6fa`) and white data surface (`#fff`) keep examples legible. Main ink is `#202b41`, secondary ink `#657389`.

## Typography
Self-hosted Vazirmatn handles Persian copy, with Tahoma as fallback. Headings are 26–38px; body copy is 13px with generous line height. Tabular figures help time and amounts line up. The font's SIL OFL notice lives beside the font file.

## Layout
Desktop: sticky 280px sidebar on the right and a flexible reading pane on the left. Mobile (≤760px): right-side drawer with backdrop, Escape and close controls. Without JavaScript the sidebar becomes an in-flow list above content. Tables reflow into labeled rows at ≤600px. Collapsed desktop rail retains group icons; choosing one expands and opens that group.

## Elevation & Depth
Surfaces have a quiet one-way shadow (`0 10px 26px rgba(26,45,79,.05)`) and thin borders. The sidebar is separated by a broader, soft offset shadow, not glow.

## Shapes
Navigation uses 8–9px rounded corners, samples 11–14px. Form-like visual placeholders are not interactive controls.

## Components
- **Navigation:** five grouped toggles with local line icons, a filled active link, and `aria-expanded` state. Direct loading opens the current group.
- **Demo badge and notice:** every page says its content is fictional and display-only.
- **Tables:** real table semantics on desktop; labeled stacked rows on phones, never silently clipped columns.
- **Contract preview:** one partial shared by draft and archive routes.

## Do's and Don'ts
- Do preserve exact Persian issue labels and obvious keyboard focus.
- Do mark every fictional record and status as a sample.
- Don't add fake working search, persistence, login, or live status to this phase.
