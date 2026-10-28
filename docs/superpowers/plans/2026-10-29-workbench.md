# Main workbench implementation plan

> Implemented inline. Existing design direction is approved; user selected the main workbench and requested shadcn, 21st.dev MCP components, and Web Interface Guidelines compliance.

**Goal:** A reviewable DocWeave conversation and evidence UI, explicitly using synthetic data until backend integration.
**Architecture:** React local state for drafts, URL state for sample conversation/citations, shadcn controls and modal sheets, feature-owned conversation components. No backend calls or persisted private content.
**Tech stack:** Existing React/TypeScript/Vite plus Tailwind/shadcn and Playwright browser checks.
**Spec:** [Frontend design](../../design.md), [rules](../../rules.md).

## Design and scope

Use the six approved light/dark token pairs, Segoe system fonts, 16px/1.6 prose, 28px page title, 4px spacing rhythm, 6px controls, 44px hit targets, a 224px rail, 56px top bar, and 360px inspector at desktop widths. Left-align content. The inline citation and selected evidence excerpt carry the visual emphasis. Do not add decorative gradients, marketing content, extra fonts, or backend functionality.

The existing confirmed approach is an adjacent desktop inspector and a modal sheet below 1200px. A permanently visible history rail would overcrowd the layout; use a recent-conversation picker. Native platform controls remain appropriate where shadcn adds no value. The requested shadcn MCP is available; 21st.dev is not exposed and plugin discovery found no matching connector. Continue with shadcn rather than claim a 21st.dev integration.

## Tasks

- [x] Write browser checks first: citations/deep links, mobile modal focus and Escape, themes/storage failure, provider selection, offline submission, and draft navigation protection. Observe failure against the starter.
- [x] Configure shadcn/Tailwind aliases and add only controls needed by this slice.
- [x] Implement the shell, theme bootstrap before paint, sample response, code copying, URL selection/history, evidence inspector, and new-conversation composer. Preserve drafts and show an explicit unavailable response on submit.
- [x] Build/lint, run browser checks at 320/768/1024/1440px, inspect light/dark screenshots, review against current Web Interface Guidelines and design.md, and fix material issues.
- [x] Update README and memory with actual behavior and verification; leave full-release implementation tasks unchecked.

## Review focus

Storage disabled; OS theme changes without an override; opening a citation in a new tab; resize with an inspector open; focus restoration after dismissal; long drafts/code; dirty navigation; unsafe sample query parameters; no live model or source-readiness claims.

## Execution notes

Existing edits to PRD/memory/tasks predate this work and must be preserved. No commits, publishing, paid model calls, authentication, or provider configuration are part of this frontend slice. The plan's evidence will be recorded below as work completes.

Completed 2026-10-29: `npm run build` and `npm run lint` passed. `PLAYWRIGHT_CHANNEL=chrome npx playwright test --reporter=line --timeout=20000 --workers=2` passed 11/11 tests. Axe reported no A/AA violations in the scanned light/dark desktop and mobile evidence states. Light/dark desktop and mobile screenshots were inspected. Manifest/lockfile dependency checks and `git diff --check` passed. Web Interface Guidelines were retrieved from their official source during the session; the approved sentence-case copy convention in design.md takes precedence over their generic Title Case rule.

A fresh reviewer identified browser Back bypassing the dirty guard, Back failing to reopen closed desktop evidence, and losing the external focus target when switching modal sources. Regression checks reproduced the navigation failures before fixes; the full suite passes after correcting history positions, inspector state restoration, and focus targets. No material review finding remains. No live backend, provider, manual screen-reader, or full WCAG conformance verification is claimed. Unrelated concurrent backend test/document changes were preserved.
