# Repository-wide dependency discovery

Status: approved by the user on 2026-11-02; implemented and verified on 2026-11-03.

## User outcome

A single repository-root project discovers dependency metadata for all apps in that repository, including SwapKr's `backend/` and `client/`. Selecting an application folder restricts discovery to that subtree. The project retains its immutable repository/branch/folder binding.

## Smallest complete implementation

- Extend the existing bounded, commit-pinned scanner to discover allowlisted metadata beneath the selected folder. Ignore dependency installations, virtual environments, VCS and generated build directories. Never fetch or execute application source.
- Parse each manifest directory with the existing Python/npm/pnpm parsers and nearest supported ancestor lock rules. Keep the current file/tree/byte/request limits across the entire scan. Unsupported or malformed required metadata makes the whole scan incomplete and preserves last good project memory.
- Add the repository-relative application folder to each dependency's existing JSON record. Fingerprints and stable dependency IDs include that folder, so the same package in different apps can retain different versions and independent documentation choices. Existing entries without a folder mean repository root.
- Show the folder beside dependencies in Project documentation. Reuse the current project stack, catalog matching, readiness, consent and retrieval flows; do not add a second project hierarchy or database table.
- Preserve explicit incomplete results for unsupported workspace links, patched packages, unresolved/ambiguous versions within one app, and unsupported lock formats. Repository-wide discovery does not imply support for every package manager.

## Reach and compatibility

Changes reach repository metadata selection, stack parsing/fingerprints, project-memory IDs, documentation coverage output/UI, checked API contract if needed, tests and current runbooks. Existing project/conversation APIs and processing approvals remain. No repository rebinding, paid call, source-code ingestion or automatic source approval is introduced.

## Acceptance

Tests cover backend/client discovery at one SHA, subtree isolation, nearest ancestor locks, exclusion of generated/vendor directories, app-specific versions/IDs, independent documentation choices, deterministic no-op fingerprints and last-good preservation on any partial scan. Run a serial combined backend suite plus frontend build/lint/browser checks. Verify the real SwapKr root project through the live queue once the current verified schema migrations are safely applied; record actual results and retain disabled provider gates.

Verified 2026-11-03: backend681, frontend19/build/lint pass; independent re-review clean. Restore-tested development0040 cutover and original live SwapKr sync complete;92 directly declared records across both apps, same-commit reuse verified, zero provider calls/charges.

Dependency scope (2026-11-03): retain only packages directly declared by each app. Preserve runtime/development/optional/peer roles, app folders and exact locked versions. Do not collect transitive packages. npm/pnpm/uv use the same policy; Python locks must identify declared roots rather than treating every cached package as a root. A scan-policy revision forces a rebuild of older scans.

Final direct-only verification: backend681 passed in224.50s (warnings as errors; logs/direct-only-final.xml). Scanner/memory163 passed and peer resolution re-review is clean. Live SwapKr ready at context4 with92 directly declared records (backend23/client69), no duplicate IDs, same-commit reuse, zero provider calls/charges. Frontend unchanged for this scope reduction; prior19/build/lint verification remains applicable.
