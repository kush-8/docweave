# Worker recovery implementation plan

**Goal:** Recover original durable work after interruption without repeating uncertain paid calls or reviving deleted work.

**Spec:** Personal-project plan, synchronization and waiting turns; docs/tasks.md worker-recovery acceptance. User requested implementation and an in-progress status.

**Approach:** Extend existing personal jobs, queue maintenance and provider journal. Reuse project serialization, worker leases and current authorization callbacks. No new queue, paid evaluation or development migration. Preserve concurrent catalog/sync work.

- [x] Add failing interruption/restart/duplicate-delivery tests. Preserve interrupted leases and run bounded periodic reconciliation using existing stalled-queue recovery APIs.
- [x] Add failing provider-checkpoint tests. Persist successful responses privately, reuse only exact scoped requests after current authorization/consent/profile checks, and never retry a claim without a durable response.
- [x] Exercise deletion/cancellation and changed-context waits, including paid resolution reuse and current release checks. Add only necessary additive migration(s), repository functions and caller updates.
- [ ] Run focused tests and serial backend verification; record failures and concurrent integration limits. Keep the grouped task in progress pending complete operational acceptance.

Boundaries: no provider calls, credentials/settings edits, development migration/reset, deployment or unrelated catalog changes. Old assistant answers remain outside evidence. Durable provider responses are private recovery checkpoints, not a semantic answer cache.

## Verification

Focused recovery/release/admitted-answer checks: 8 passed; the broader focused recovery/sync/catalog set passed 16 before adding final release fences. Full coordinated serial backend suite: 469 passed in 141.70 seconds with warnings as errors. Guarded disposable Alembic model/schema check reports no new upgrade operations. Independent reviewer stopped at a usage limit; manual review covered lease/cancellation, duplicate delivery, profile/consent, unknown claims, checkpoint privacy, deletion lock order and context-release checks. Fresh independent review remains pending. No live process-kill/restart, provider/GitHub calls or development migration was performed. The grouped task remains in progress for remaining operational acceptance. Twenty local documentation links and whitespace checks pass.

## Decisions

Recovery is checkpoint reuse, not paid retry. A stage with no saved response blocks new calls with that stage key, even after request/context changes. Legacy calls without keys conservatively block the same actor/project until operator reconciliation. Known successful responses may be reused after current checks, and all cost/uncertainty claims remain intact. Private checkpoint deletion maps the four existing AnswerEngine stage keys; new private stages must extend that deletion/liveness mapping.

Additive migrations: 0031 stores response/stage checkpoints; 0032 adds bounded duplicate-safe queue reconciliation; 0033 fences stale publication and deletion/late writes. Existing migration/code commits made by concurrent chats were preserved.
