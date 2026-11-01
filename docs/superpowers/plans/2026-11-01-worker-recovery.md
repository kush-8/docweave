# Worker recovery implementation plan

**Goal:** Recover original durable work after interruption without repeating uncertain paid calls or reviving deleted work.

**Spec:** Personal-project plan, synchronization and waiting turns; docs/tasks.md worker-recovery acceptance. User requested implementation and an in-progress status.

**Approach:** Extend existing personal jobs, queue maintenance and provider journal. Reuse project serialization, worker leases and current authorization callbacks. The user separately authorized final review, process-kill acceptance and the backed-up development migration through 0033. No new queue or paid evaluation. Preserve concurrent catalog/sync work.

- [x] Add failing interruption/restart/duplicate-delivery tests. Preserve interrupted leases and run bounded periodic reconciliation using existing stalled-queue recovery APIs.
- [x] Add failing provider-checkpoint tests. Persist successful responses privately, reuse only exact scoped requests after current authorization/consent/profile checks, and never retry a claim without a durable response.
- [x] Exercise deletion/cancellation and changed-context waits, including paid resolution reuse and current release checks. Add only necessary additive migration(s), repository functions and caller updates.
- [x] Run focused tests and serial backend verification, independent review, real process-kill/restart acceptance and the separately authorized development restore rehearsal/cutover. Record concurrent integration failures separately.

Boundaries: no provider calls, credentials/settings edits, data reset, deployment or unrelated catalog changes. Development migration stops at the separately authorized, rehearsed 0033 target; later source migrations are excluded. Old assistant answers remain outside evidence. Durable provider responses are private recovery checkpoints, not a semantic answer cache.

## Verification

Independent review is clean after fixing concurrent stalled retry and healthy re-fetch races. The repository locks the delivery and rechecks current worker heartbeat/status before retry. A real child process is killed while leased, then a real queue worker restarts: actual queue heartbeat expiry, a controlled shortened application lease and the periodic sweep complete the original job once. No provider requests/charges occur. The concurrency and process acceptance checks pass (2 tests in 46.12 seconds); the full combined backend run passes recovery checks, with 539 passed and 3 failures in concurrent catalog/0034 work (pending downgrade predicate and catalog receipt URL/digest alignment). These are not a clean release-suite claim.

Development is migrated through 0033 after API drain, a private full dump/artifact copy, actual isolated restore and rehearsed upgrade. Original rows/artifacts match exactly except the expected Alembic revision; canonical columns/functions/grants/sequences match the rehearsal and all three restricted logins pass. Raw ACL comparison initially differed only because pg_restore represented explicit owner-full rights as implicit default owner rights; canonical effective permissions are equal. The temporary rehearsal database is removed and private backup/evidence retained. API and Vite proxy liveness return 200; readiness remains 503 and unauthenticated identity reads return 401. No workers, paid profiles or later source migrations were enabled by this task. Worker recovery acceptance is complete; broader release acceptance remains separate.

## Decisions

Recovery is checkpoint reuse, not paid retry. A stage with no saved response blocks new calls with that stage key, even after request/context changes. Legacy calls without keys conservatively block the same actor/project until operator reconciliation. Known successful responses may be reused after current checks, and all cost/uncertainty claims remain intact. Private checkpoint deletion maps the four existing AnswerEngine stage keys; new private stages must extend that deletion/liveness mapping.

Additive migrations: 0031 stores response/stage checkpoints; 0032 adds bounded duplicate-safe queue reconciliation; 0033 fences stale publication and deletion/late writes. Existing migration/code commits made by concurrent chats were preserved.
