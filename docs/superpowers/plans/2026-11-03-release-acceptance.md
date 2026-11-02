# Release acceptance execution

**Goal:** complete the remaining work in `docs/tasks.md` without treating mocked tests, pending invoices or machine reviews as release evidence.

**Architecture:** keep the current personal API, narrow database functions and worker maintenance. Preserve financial IDs, original archives, current authority checks and unknown-completion replay fences. No new dependencies or infrastructure.

**Spec:** `docs/PRD.md`, `docs/tasks.md`, `docs/runbooks/budget.md`.

## Billing and provider activation

- [x] Record Groq October usage and pending invoice status using its verified monthly/minimum-charge billing terms. Save observations privately with per-reservation pending/settled dispositions. User explicitly skipped further Google billing review; Gemini claims remain unresolved and cannot be replayed.
- [x] Verify the selected OpenAI/Groq models/prices and five fixed synthetic contracts. User explicitly approved those five within US$0.01 without waiting for final historical invoices; all five passed. Four selected profiles record verification and remain disabled. No private activation or broader evaluation authority is inferred.
- [ ] Verify live summary capability and deliberately activate effective SwapKr-only private consent/profiles/generation. A separate disabled summary profile/ID is prepared. No automatic replay or expansion to other projects.

## Retention and recovery

- [x] Trace retained tables/functions against financial, operator and restoration callers. Audit and live counts/grants identify retirement candidates, but no wholly unreferenced group is safely removed in this change.
- [x] Reproduce retained deleted-chat message/answer/citation content in a real disposable-database regression. Test owner isolation, idempotence, late publication fences and financial preservation.
- [x] Add migration `0041_chat_cleanup`: erase content on explicit chat deletion and expose a worker-only bounded reconciliation for existing tombstones. Preserve IDs, ledger, hashes and recovery/replay identity. Existing recovery also expires bounded batches of auth secrets.
- [x] Reuse artifact reconciliation in personal-worker startup/maintenance, testing orphan removal and retained snapshots with real storage. Reproduce and fix concurrent cleaner disappearance.
- [x] Verify migration roundtrip, restricted grants, focused recovery/deletion checks and the serial backend suite (702 passed). Development0041 passed an actual backup/restore rehearsal and preservation comparison. Personal-worker heartbeat and API/proxy health are verified.
- [x] Document the seven-day backup expiry gap and protect unresolved-accounting archives from automatic deletion. Do not claim full retention acceptance from chat erasure alone. Automatic expiry/post-restore deletion policy remains open.

## Release evaluation

- [x] Preserve the hash-pinned development pilot; prepare a separate 150-case draft, strict 100/50 loader and family/hash/mutation checks. Labels, source spans, executable multi-turn/access fixtures and held-out sealing remain pending.
- [ ] Capture the actual personal answer pipeline, top-10 retrieval and exact citations; report fact coverage, abstention, false positives, latency and incurred/uncertain cost with denominators.
- [ ] Produce separate 30-output human review packets. Human review and a budget covering the concrete full workload remain prerequisites to paid execution; synthetic probes do not cover it.
- [x] Keep readiness 503 until all evidence meets the PRD criteria. Semantic caching remains a later measurement-based discussion.

## Verification focus

Deletion must not erase active or another owner's content, ledger entries or operation IDs; deleted jobs must not publish late. Startup must reconcile prior tombstones without needing owner login. Artifact cleanup must retain referenced snapshots and the write grace period. Held-out cases cannot be used for tuning. Pending external evidence must keep activation and readiness disabled.
