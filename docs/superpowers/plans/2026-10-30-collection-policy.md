# Collection grants and processing approvals

> **For agentic workers:** Use superpowers:executing-plans in this session, test first, with one independent read-only final review.

**Goal:** Implement the eight existing collection create/list, collection grant read/replacement, and project/collection processing-policy read/replacement operations.

**Architecture:** Reuse actor/tenant sessions, encrypted keyset pagination, strict input schemas and workspace-lock owner revalidation. Narrow fixed-search-path SQL functions enforce grants/revisions and processor identity; no general runtime domain writes. Collection RLS enforces current membership plus owner/grant access. Metadata-only processor registration is operator-controlled and immutable; approval does not enable inference or bypass later capacity/processor checks.

**Spec:** [architecture](../../architecture.md#identity-tenancy-and-grants), [API](../../../backend/openapi.yaml), [Task 1](../../tasks.md#task-1--reproducible-runtime-and-real-access-boundaries).

## Constraints and reach

- Work on user-selected `main`, backend only, building on committed project baseline `9a12254` and preserving unrelated work. No frontend, provider requests, persistent development DB, commit/push or deployment.
- Modify models, policy/main registration, shared revision error wording, disposable fixture cleanup, prior stub assertions and status docs. Add `collections.py`, revision `0006_collection_policy`, `test_collections.py` and a runbook. No new dependencies.
- Owners create/manage all collections. Other members see only granted collections. Write requires owner or maintainer plus write grant; grants never elevate a member's role.
- Complete grant and processor replacements use independent positive integer revisions; stale writes return 409. New collections/policies start owner-only/empty.
- Membership removal deletes grants; demotion to member downgrades write grants to read and advances affected grant revisions. Rejoining/promotion cannot resurrect removed write access.
- Project and collection approvals remain independent. Only enabled operator-registered immutable actual processor/backend IDs may be approved; empty replacement always revokes all. Registration is metadata, not account/model/price verification. There is no hosted-call path yet.
- Existing histories/workers do not exist; later consumers must use these current policy checks rather than copied grants. No pause-worker implementation is claimed.

## Review focus

- Cross-tenant/hidden collection IDs must return 404 with no names or member lists.
- Grant removal, role demotion and membership removal must immediately affect reads/writes and cursors.
- Concurrent replacements and ownership loss during lock waits must not overwrite policy or grant authority.
- Duplicate, nonmember, wrong-role grants, null/NUL/extra input and unknown/disabled processor IDs must fail atomically.
- Processor identity must not be repointed; approval at one scope must not silently approve another or permit hosted calls.

## Task 1: Access and consent APIs

**Interfaces:** Existing eight target operations; `require_collection_actor`, `require_collection_owner`, `require_collection_writer`; SQL `collection_can(uuid,text)`, `collection_workspace(uuid)`, `create_collection(uuid,text)`, `collection_grants(uuid)`, `replace_collection_grants(uuid,integer,jsonb)`, `processing_policy(text,uuid)`, `replace_processing_policy(text,uuid,integer,jsonb)`. Private membership-grant and immutable-processor triggers support their invariants.

- [x] Write behavioral/security/revision/race tests; observe missing behavior before implementation.
- [x] Implement storage, default revisions, private approval/grant rows, operator processor registry, scoped SQL functions/RLS/triggers and eight handlers. Reuse existing helpers and update affected callers/fixtures.
- [x] Run targeted then full backend suite with warnings as errors, migration round-trips/model alignment, lockfile/Compose/whitespace/link checks.
- [x] Obtain independent review, resolve material findings regression first, update evidence/handoff and stop disposable PostgreSQL.

## Evidence

- Approval-service usage limits initially blocked starting test PostgreSQL; no bypass was attempted. After the user confirmed restored capacity, authorized execution resumed. Docker Desktop was stopped, so it was started hidden and only the disposable service was brought up.
- RED: **31 cases failed** against existing stubs. GREEN: all 31 passed, then the first full suite passed **365 tests** with warnings as errors. Extra ACL/input/rollback/disable-wait/schema coverage was added. A private-trigger ACL test initially hit the driver's unsupported trigger result type; selecting a boolean expression verifies the same denied execution correctly.
- Independent review found one P2: a VOLATILE policy reader could combine old authorization/revision with newer IDs. All three forced-interleaving regressions (project, collection, grant revocation) failed first, exposing the mixed state. Marking the reader STABLE keeps one snapshot; nested replacements still see their own writes. Reapplied the uncommitted migration through disposable downgrade/re-upgrade, then **49 checks passed** (48 collection cases plus the explicit migration round-trip).
- No other material review findings or deferred minor findings. Persistent development credentials and legacy-stack inventory remain unverified; only guarded disposable PostgreSQL was used.
- Final: `uv run --project backend --locked --cache-dir backend/.uv-cache pytest backend/tests -q -W error --tb=short` -> **382 passed in 72.34s**, including **48 collection cases**. Full output is ignored local `backend/.uv-cache/collection-final.log`.
- `uv lock --project backend --check --offline --cache-dir backend/.uv-cache` resolved the unchanged 65-package lock. `docker compose --profile auth --profile test config --quiet` and `git diff --check` passed (only the existing LF/CRLF checkout notice). Changed Markdown local links/fences and new-file whitespace passed. Disposable PostgreSQL stopped after verification. No frontend, persistent DB, commit/push/deployment or paid calls.
