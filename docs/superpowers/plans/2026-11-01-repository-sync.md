# Repository sync implementation plan

**Goal:** Retry blocked initialization asynchronously in the same chat and resolve supported monorepo locks without asserting incomplete metadata is current.

**Spec:** [Personal-project plan](2026-10-31-personal-github-projects.md), synchronization and waiting turns. The user selected sync retries and pnpm/monorepo support and confirmed retries should be asynchronous.

**Architecture:** Reuse durable personal jobs, project advisory locks, restricted database functions and commit-pinned metadata transport. No HTTP retry loops, package execution, paid calls or development migration. Keep existing uncommitted preservation work.

**Approach:** Extend the existing scanner and queue. Reuse installed PyYAML with bounded safe parsing for pnpm v9; scope each lock to the selected importer. A generic package-manager resolver or package installation would add execution and infrastructure outside the approved scope.

## Work

- [x] Add failing parser/transport tests for pnpm v9, selected ancestor importers, npm workspace resolution, stale/malformed/unsupported locks and sibling isolation. Implement the smallest bounded static parsing; declare the existing YAML dependency for runtime use.
- [x] Add failing database/API tests for same-chat asynchronous sync retry, duplicate requests, owner/CSRF/deletion gates, and useful failure reasons. Add migration 0028, restricted retry RPC, repository call and HTTP 202 route. Preserve current citation release protections and memory on failure.
- [x] Add failing browser test, then expose retry and safe progress using existing components/polling. Update the checked API contract and current docs.
- [ ] Verify force-push commit pinning, serialized refresh, partial-scan preservation and recovery. Run serial backend tests, frontend browser/build/lint, lock and whitespace checks. Record actual results and remaining limits.

## Review focus

YAML duplicate keys/aliases/tags and resource bounds; stale manifest versus lock; sibling package contamination; concurrent retry deduplication; expired/deleted/unauthorized jobs and stale publication. Test these at parser, actual disposable database and browser boundaries.

## Decisions

- Support pnpm lockfile v9 registry packages and npm v2/v3 ancestor locks. Other lock versions, workspace-linked dependencies, catalog specifiers and ancestor uv/Poetry/Yarn mappings remain explicitly incomplete until their semantics are supported.
- Retries are explicit user actions on blocked initialization; they enqueue metadata-only work and never replay answer/provider operations.
- Use the existing working directory to preserve the user's uncommitted preservation changes; do not commit unrelated work.
- Concurrent work committed/applied 0028 during implementation. Keep its schema semantics; the grant statements are split for asyncpg compatibility. Add the later stale-publication return fix in 0029 instead of changing applied function behavior in 0028. Concurrent documentation-review migration 0030 follows 0029.
- Hold overlapping installed versions and patched packages incomplete; the existing memory identity cannot safely represent multiple versions for the same technology/role. Include npm installed peers and allow missing explicitly optional peers.

## Verification and open acceptance

Focused GitHub/scanner/retry/worker suite: 73 passed with warnings as errors. Sync frontend checkpoint: 14 Chrome tests passed, build/lint passed. Lock consistency, 13 documentation links and whitespace checks passed. Independent review found no remaining actionable sync defects after regression fixes. Selected-app scans skip unrelated ancestor ecosystem locks.

Combined backend run: 449 passed, one contract failure for two concurrent documentation-review routes not yet represented in the checked contract. An earlier public-pilot replay failure passed in isolation. A transient multiple-head failure during concurrent migration edits is resolved by chaining documentation review after 0029. No live GitHub/provider check, development migration, paid call or deployment was performed by this sync work. Keep the grouped task in progress as the user requested; broader format support and live operational acceptance remain open.
