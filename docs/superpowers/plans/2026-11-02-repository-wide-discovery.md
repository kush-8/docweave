# Repository-wide discovery implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** One repository project discovers all nested app dependencies without mixing their versions or documentation selections.

**Architecture:** Extend bounded metadata discovery and reuse the existing per-app parsers. Store app-folder identity in existing dependency JSON and stable IDs; keep current APIs, queues and authorization.

**Tech stack:** Existing Python, SQLAlchemy/PostgreSQL JSON, React/TypeScript and Playwright; no new dependencies.

**Spec:** [Approved design](2026-11-02-repository-wide-discovery-design.md).

## Global constraints

- Never fetch/execute repository source or run package managers.
- Keep current file/tree/byte/request limits across the entire scan.
- Preserve last good memory when any required scan is incomplete.
- Keep immutable repository bindings, explicit processing consent and disabled paid gates.
- Do not run shared database tests during another chat's reserved window.

## Review focus

- Different app folders using different versions must retain distinct dependency IDs and documentation choices.
- A selected subtree must not incorporate siblings; nearest ancestor locks must still work.
- Generated/vendor folders must not create dependencies or false failures.
- Malformed/unsupported metadata in one discovered app must prevent partial publication.
- Legacy root records and no-op scans must retain stable identities.

## Task 1: Discover and parse nested apps

Current ruling: retain directly declared packages with their app folders, roles and exact locked versions. Missing declared optional packages remain version-unresolved; unresolved required declarations block publication. Transitive packages are outside discovery scope.

Files: `integrations/github.py`, `integrations/stack.py`, `services/repository_sync.py`, `tests/github/test_repository_discovery.py`.

- [x] Add failing real parser and mocked transport tests for multi-app root/subtree scopes, nearest locks, exclusions, folder/version identity, deterministic ordering and incomplete child metadata.
- [x] Extend metadata selection under the selected folder; use one shared exclusion predicate and existing total limits.
- [x] Reuse per-directory parsing, append `application_path` to dependencies and compute one deterministic aggregate fingerprint. Preserve unsupported lock/link/ambiguous-version results within each app.
- [x] Run focused parser/transport tests; update intentionally changed root-workspace expectations.

## Task 2: Preserve app identity through memory and documentation

Files: `services/project_memory.py`, `services/catalog.py`, `components/DocumentationReview.tsx`, corresponding Python and browser tests.

- [x] Add failing memory tests for distinct folder IDs, legacy-root identity and no-op/version-change behavior.
- [x] Include folder in stable dependency keys; expose folder in documentation coverage and display it beside technology/version using existing UI.
- [x] Verify documentation choices remain bound to the correct dependency ID and target, and that mixed versions are not silently merged.
- [x] Run focused memory/coverage/browser checks.

## Task 3: Combined and live acceptance

- [x] Obtain explicit shared DB release; run serial combined backend checks and fix material integration failures.
- [x] Run frontend build/lint/browser suite and lock/whitespace checks.
- [x] After verified 0039/0040 backup/restore rehearsal and safe development cutover, process the original SwapKr sync intent through the real queue with provider keys disabled.
- [x] Verify same-commit no-op reuse and safe retry behavior without changing upstream code or paid claims.
- [x] Update PRD/runbooks/task status and actual evidence. Keep unsupported formats and wider release requirements explicit.

Review follow-ups: preserve legacy scoped IDs using the immutable project binding; seed installed direct npm peers; retain standalone uv.lock directories; version aggregate fingerprints so old same-commit scans rebuild once. All regressions reproduced before fixes; focused95 pass and independent re-review is clean. Combined and live acceptance completed; current scope is recorded below.

Verified 2026-11-03: backend681, frontend19/build/lint pass; independent re-review clean. Restore-tested development0040 cutover and original live SwapKr sync complete;92 directly declared records across both apps, same-commit reuse verified, zero provider calls/charges.

Dependency scope (2026-11-03): retain only packages directly declared by each app. Preserve runtime/development/optional/peer roles, app folders and exact locked versions. Do not collect transitive packages. npm/pnpm/uv use the same policy; Python locks must identify declared roots rather than treating every cached package as a root. A scan-policy revision forces a rebuild of older scans.

Final direct-only verification: backend681 passed in224.50s (warnings as errors; logs/direct-only-final.xml). Scanner/memory163 passed and peer resolution re-review is clean. Live SwapKr ready at context4 with92 directly declared records (backend23/client69), no duplicate IDs, same-commit reuse, zero provider calls/charges. Frontend unchanged for this scope reduction; prior19/build/lint verification remains applicable.
