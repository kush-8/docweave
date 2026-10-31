# Workbench design

The current UI is a personal project workbench: GitHub sign-in, Projects sidebar, repository/goal setup, project-required New chat, durable conversation history, Composer, processing permissions and authorized citation evidence. No pricing, workspace, role or sharing UI.

`pages/WorkbenchPage.tsx` coordinates API state; `layouts/` owns shell/header/sidebar; `components/` owns setup, permissions, composer and dialogs; `hooks/` owns draft/navigation/theme behavior; `routing/workbench.ts` owns URLs; `data/api.ts` owns HTTP contracts. Synthetic production conversation/evidence components are removed. Deterministic browser mocks live only under `tests/support/`.

Keep draft protection for navigation/new chat/sign-out, keyboard and screen-reader access, responsive layouts at narrow/tablet/desktop widths, and light/dark themes. Private project/chat data stays in memory; only theme preferences use localStorage. Abort/session-generation guards prevent stale responses from repopulating signed-out state.

Show actual server sync/turn stages and context-change notices. Indexing is indeterminate unless measurable. Show source-dependent waiting only for identified requirements with active work, never low confidence alone. Errors preserve the draft and idempotency key; evidence opens through an authorized endpoint. Installation/status/retry, coverage/fallback review and recovery paths still need complete acceptance; do not invent supported flows in copy.

Use the current [API guide](api.md), [setup guide](runbooks/personal-projects.md) and [remaining tasks](tasks.md). Verification: frontend build/lint and Playwright architecture/e2e/accessibility tests. Mocked HTTP does not prove live integration.
