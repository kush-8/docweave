# Documentation review implementation plan

**Goal:** Expose truthful project documentation coverage, explicit revision-bound fallback acceptance and operator-only public source review.

**Spec:** [Approved personal-project plan](2026-10-31-personal-github-projects.md), catalog/version review and distinct source states.

**Architecture:** Extend the existing catalog matcher, restricted SQL functions, shared jobs and project UI. Source approval and fallback acceptance are separate: owners choose coverage for their project; only the operator publishes/reviews public sources. Existing private imports keep their source/consent/assessment gates. No public administration UI, new dependency or paid calls. The later user instruction to complete the task includes the verified development migration.

## Work

- [x] Add focused failing tests for truthful catalog states, selected fallback reuse and version-change invalidation. Extend catalog models/migration with package aliases and the exact dependency target accepted by the owner.
- [x] Add owner/CSRF/current-repository-gated coverage and selection endpoints. Validate context revision, dependency identity, immutable source revision and actual version coverage in SQL; reuse deduplicated catalog ingestion. Cover revocation, stale acceptance, isolation and selection removal.
- [x] Add operator manifest review/publication tooling, bounded source validation and real publisher-pinned examples. Unknown public origins remain unapproved until an explicit reviewed replacement revision is published; no lookup of private dependency names.
- [x] Add a project documentation panel using existing controls. Show missing, approval, capacity, processing, failure and ready states; require explicit fallback acceptance and preserve drafts.
- [x] Run serial disposable-database integration tests after concurrent sync work releases that database, backend suite, frontend browser/build/lint, contract/whitespace checks. Update current docs and mark the task done only when its acceptance passes.

## Review focus

- A fallback accepted for one target must not authorize another target after repository sync.
- A private selection cannot approve/publish public sources or replay uncertain paid work.
- Exact coverage, canonical package aliases and selected generation must agree at selection and evidence release.
- Failed, capacity-blocked, revoked or quarantined sources must not appear to be actively indexing.
- Operator source publication must preserve immutable provenance and never fetch unreviewed origins automatically.

## Execution

Implement inline under the existing user-approved direction and TDD preference. Preserve concurrent sync edits and leave commits to the user. Development migrations 0034–0037 were backed up, restored and rehearsed before cutover.

The grouped task is complete: explicit-consent publisher discovery, actor/project/context-bound private review, bounded static HTML and durable consent-gated private indexing are implemented. All 29 entries/85 official pages passed robots, bounded fetching and actual parsing; rolling references remain distinct from exact version compatibility. Backend 574 passed; browser 18 passed; build/lint and independent review passed. Development is verified through 0037 with original rows/artifacts and canonical schema/grants/sequences matching the restore rehearsal. Shared selection/release checks cover deselection, changed accepted targets and disabled generations.
