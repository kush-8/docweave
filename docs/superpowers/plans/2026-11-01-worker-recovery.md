# Worker recovery implementation plan

**Goal:** Recover original durable work after interruption without repeating uncertain paid calls or reviving deleted work.

**Spec:** Personal-project plan, synchronization and waiting turns; docs/tasks.md worker-recovery acceptance. User requested implementation and an in-progress status.

**Approach:** Extend existing personal jobs, queue maintenance and provider journal. Reuse project serialization, worker leases and current authorization callbacks. No new queue, paid evaluation or development migration. Preserve concurrent catalog/sync work.

- [ ] Add failing interruption/restart/duplicate-delivery tests. Preserve interrupted leases and run bounded periodic reconciliation using existing stalled-queue recovery APIs.
- [ ] Add failing provider-checkpoint tests. Persist successful responses privately, reuse only exact scoped requests after current authorization/consent/profile checks, and never retry a claim without a durable response.
- [ ] Exercise deletion/cancellation and changed-context waits, including paid resolution reuse and current release checks. Add only necessary additive migration(s), repository functions and caller updates.
- [ ] Run focused tests and serial backend verification; record failures and concurrent integration limits. Keep the grouped task in progress pending complete operational acceptance.

Boundaries: no provider calls, credentials/settings edits, development migration/reset, deployment or unrelated catalog changes. Old assistant answers remain outside evidence. Durable provider responses are private recovery checkpoints, not a semantic answer cache.
