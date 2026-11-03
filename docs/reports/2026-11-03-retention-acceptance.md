# Retention operational acceptance

Development is verified through migration `0045_retention_acceptance`. Retention operational acceptance passes; full release evaluation and private activation remain unfinished.

Actual isolated PostgreSQL and Windows child-worker tests reproduced overdue backlogs surviving startup/periodic maintenance, checkpoint-only chat payloads surviving cleanup, private embedding responses/document titles surviving deletion, and private requests remaining available after an artifact deletion failure. The fixes drain overdue batches before queue startup, repeat the drain at each maintenance tick, erase payloads while preserving financial/replay identity, and require a fresh successful maintenance record for protected requests and hosted dispatch. Recorded deleted artifacts bypass the grace period for unknown recent writes, including freshly restored files.

The maintenance record contains only a database/storage/journal binding and outcome/time. API startup requires a strictly later successful worker pass, including when Windows clock ticks coincide. Protected traffic rejects failed, missing, malformed or older-than-30-second records and overdue database cleanup. Shared monotonic time and local files assume the current single-host deployment. Distributed workers require database-backed health.

Independent review found that a pending backup expiry closed request gates while periodic queue consumption continued. The new failure path stops consumption and sets the queue's shutdown grace period to zero, cancelling active async tasks. Actual idle/active worker regressions passed, including recovery of the same durable job after lease expiry and unchanged financial claims. Already admitted or in-flight external bytes cannot be recalled.

Actual isolated PostgreSQL and Windows child-process tests cover 205-row startup/periodic backlogs, file locks, sealed backup expiry failure, cancellation/restart, checkpoint-only chat tombstones, and legacy document cleanup with fresh restored artifacts. A serial backend run passed **761 tests in 352.61 seconds**, with warnings treated as errors and independently confirmed zero failures/errors/skips.

Each personal/catalog/private-index/rescan wrapper also requires current retention before its domain claim. Seven wiring/admission checks pass, including a real rejected delivery recovering the original job ID after cleanup. Final serial verification passed **766 tests in 357.65 seconds**, with warnings as errors and independently inspected zero failures/errors/skips (`logs/retention-admission-final-20261103.xml`). Independent review found no remaining actionable issue.

The actual development backup was restored and upgraded in isolation before the original database. Every retained row and artifact matched; only the migration revision changed. Functions, triggers, grants, columns and sequences matched the accepted rehearsal, and all three restricted logins passed. Private evidence: `backups/retention-acceptance-20261103T111119Z/acceptance.json`. The protected accounting archive was byte-for-byte unchanged and remains unenrolled. This ninth verified ordinary backup expires November 10 at 11:11:19 UTC.

Live acceptance verifies the document erasure trigger, no overdue cleanup, current maintenance health, fresh worker heartbeat, reconciled deletion journal, zero enabled profiles, and all six claims still retaining US$0.005558110000. API/proxy liveness is 200 and readiness remains 503. Private runtime evidence: `backups/retention-acceptance-runtime-20261103.json`. Worker/API launcher PIDs are 24940/80512; children at acceptance are 54204/45552. Revalidate identities before operating them.

Git HEAD advanced externally to `f801045` during verification. This agent did not stage or commit; the external commit is preserved.

No additional paid provider calls, private activation, staging or commits were performed. Protected accounting evidence remains outside ordinary backup expiry.
