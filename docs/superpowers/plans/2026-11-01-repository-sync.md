# Repository sync implementation plan

**Goal:** Retry blocked initialization asynchronously in the same chat and resolve supported monorepo locks without asserting incomplete metadata is current.

**Spec:** [Personal-project plan](2026-10-31-personal-github-projects.md), synchronization and waiting turns. The user selected sync retries and pnpm/monorepo support and confirmed retries should be asynchronous.

**Architecture:** Reuse durable personal jobs, project advisory locks, restricted database functions and commit-pinned metadata transport. No HTTP retry loops, package execution, paid calls or development migration. Keep existing uncommitted preservation work.

**Approach:** Extend the existing scanner and queue. Reuse installed PyYAML with bounded safe parsing for pnpm v9; scope each lock to the selected importer. A generic package-manager resolver or package installation would add execution and infrastructure outside the approved scope.

## Work

- [ ] Add failing parser/transport tests for pnpm v9, selected ancestor importers, npm workspace resolution, stale/malformed/unsupported locks and sibling isolation. Implement the smallest bounded static parsing; declare the existing YAML dependency for runtime use.
- [ ] Add failing database/API tests for same-chat asynchronous sync retry, duplicate requests, owner/CSRF/deletion gates, and useful failure reasons. Add migration 0028, restricted retry RPC, repository call and HTTP 202 route. Preserve current citation release protections and memory on failure.
- [ ] Add failing browser test, then expose retry and safe progress using existing components/polling. Update the checked API contract and current docs.
- [ ] Verify force-push commit pinning, serialized refresh, partial-scan preservation and recovery. Run serial backend tests, frontend browser/build/lint, lock and whitespace checks. Record actual results and remaining limits.

## Review focus

YAML duplicate keys/aliases/tags and resource bounds; stale manifest versus lock; sibling package contamination; concurrent retry deduplication; expired/deleted/unauthorized jobs and stale publication. Test these at parser, actual disposable database and browser boundaries.

## Decisions

- Support pnpm lockfile v9 registry packages and npm v2/v3 ancestor locks. Other lock versions, workspace-linked dependencies, catalog specifiers and ancestor uv/Poetry/Yarn mappings remain explicitly incomplete until their semantics are supported.
- Retries are explicit user actions on blocked initialization; they enqueue metadata-only work and never replay answer/provider operations.
- Use the existing working directory to preserve the user's uncommitted preservation changes; do not commit unrelated work.
