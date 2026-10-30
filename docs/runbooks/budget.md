# Financial admission and configured profiles

This backend slice makes no hosted calls. It implements exact-cost reservation/reconciliation, operator monthly allowances, configured profile metadata and tenant usage. [Collection consent](collection-policy.md), provider capability/account/price checks, worker dispatch and budget are separate gates; a reservation does not authorize private-content processing.

## Read APIs

- `GET /api/v1/providers` is public and lists configured **generation/answer** profile versions, including safe disabled reasons. Internal embedding/reranking/query-resolution/summarization profiles are not answer choices. Pages use the existing encrypted cursor format (25 default, 100 maximum). No profiles are seeded/enabled by default. Unconfigured app services return 503; no hosted probe runs on GET.
- `GET /api/v1/workspaces/{workspace_id}/usage?month=YYYY-MM` requires current membership and returns only that workspace's aggregate and allowance.
- `GET /api/v1/projects/{project_id}/usage?month=YYYY-MM` requires current project access and returns project-attributed sums, with the workspace allowance and capacity status. Workspace-level operations without a project are excluded from project sums.

Both usage endpoints return decimal USD strings: `metered_usd`, `reserved_usd`, `retained_uncertain_usd`, nullable `workspace_allowance_usd`, and a safe capacity status. `allowance_required` means no monthly allocation; `workspace_limit` means the own-workspace cap is reached; `application_capacity_unavailable` is a generic shared-capacity shortage without global figures. `available` means financial headroom, not guaranteed capacity for any particular request or provider readiness. Reads use one database snapshot. Invalid months, including year zero, return safe 422; hidden scopes return 404.

## Operator configuration

Restore the original development credentials and review legacy stacks before touching persistent storage. Use only the operator/migration connection for configuration. Runtime cannot mutate caps, register/repoint profiles or read the raw financial ledger; there are no browser financial-mutation endpoints.

Assign a calendar-month workspace allowance (0–20 USD):

```sql
SELECT app.set_workspace_allowance('WORKSPACE_UUID'::uuid, '2026-11-01'::date, 1.00::numeric);
```

NULL month means the current Asia/Calcutta month, chosen after the financial lock wait. All periods begin on day one. Allocations are explicit for each month; missing next-month allocation does not inherit prior capacity. Zero stops new work, including zero-priced work. Lowering a cap never erases prior charges/reservations. Assigned caps are limits, not reserved shares of the application's US$20 monthly ceiling.

Profiles are immutable UUID versions in `app.provider_profiles`. Record exact provider/model/backend, hosted role, actual processor IDs, conservative USD input/output rates per million billable tokens, per-attempt fixed fee, maximum input/output bounds and bounded attempt count (1–10). Input/output rates and fees use exact PostgreSQL NUMERIC; use SQL decimal literals or Python Decimal from strings, never floats. Nullable/missing prices or bounds keep a profile unavailable. Do not encode expiring free credits as a zero price or configure idle-billed endpoints. Nonlinear fees must have a reviewed conservative bound, otherwise disable the profile.

The four operator flags (`enabled`, `pricing_verified`, `capabilities_verified`, `account_verified`) default false. They record verified configuration; tests do not prove real model/account/pricing behavior. Capability verification must establish enforceable framing/input and all billed output/reasoning bounds, fixed fees and retry behavior. No adapter/tokenizer/SDK/account checks or live probes were performed here. A new model/backend/processor mapping, price card or token/attempt bound needs a **new profile UUID**; flags can disable a version without repointing it.

Processor IDs must reference enabled immutable [processor records](collection-policy.md#operator-processor-metadata). At least one must match the profile's serving provider/backend/role. Generation profiles additionally expose the required Gemini embedding/reranking processors for consent; retrieval calls use their own role profiles/reservations, not the generation price. Actual call adapters and budget-reserved capability probes remain an explicit integration step before any live profile is enabled.

Planning update — 2026-10-30: the user selected Groq for all LLM roles and Gemini solely for embeddings. The preceding Gemini-reranker requirement describes the current implementation, not the new target. Task 2's follow-up must migrate eligibility to the actual role-specific processor mapping before hosted work is enabled; do not mutate historical profile UUIDs or charges. Initial synthetic compatibility probes are capped at US$0.25 total. Later RAG generation/judging suites require estimated and reserved costs under the existing tenant/global caps; a future LLM gateway is outside this release.

## Internal financial service

```python
reservation = await reserve_cost(
    actor, operation_key, profile_id, max_input_tokens, max_output_tokens,
    engine=engine, project_id=project_id,
)
await settle_cost(
    reservation.id, actual_usd, execution_uncertain,
    actor=actor, engine=engine,
)
```

Actor IDs must come from verified policy. Reserve checks current membership and same-workspace project attribution after waits. Operation keys are bounded content-free ASCII intents (for example a turn UUID plus stage/attempt), SHA-256 hashed at rest and unique per workspace across all months. A changed actor/profile/token/project payload conflicts. Exact replay returns the same ID/month/status with `created=false`; it is **not fresh dispatch permission**, including after reconciliation/month rollover. Never turn a replay/unknown outcome into a new paid call automatically.

The conservative maximum is rounded **up** to 12 decimal USD places:

```text
ceil12(((max_input * input_rate + max_output * output_rate) / 1,000,000 + fixed_fee) * max_attempts)
```

Include framing and all billable reasoning/output in token bounds. The future adapter must enforce token/attempt ceilings. Reserve immediately before work after queue waits; retries beyond the bound need a separately admitted, intentional operation. A worker still needs current content/processor/source/repository authority and a durable dispatch journal; this service does not implement provider exactly-once execution or a queue consumer.

All reserve/settle/cap changes take one transaction advisory lock, then reservation admission locks the workspace to serialize membership changes. Ledger sums, rather than cached balance counters, enforce both own allowance and shared US$20 ceiling. Admission uses the Asia/Calcutta month after waits; timestamps remain UTC and the ledger month stays fixed on later reconciliation. This records admission-month spending, not a provider's invoice calendar. No caller chooses a reservation's month.

Confirmed actual cost must be a finite nonnegative Decimal, rounded up to the same quantum. Unknown execution retains at least the reserved maximum, or a higher observed partial cost. Repeating uncertainty cannot shrink that charge. Definitive reconciliation may release the excess; repeating an identical confirmed result is idempotent, and conflicting/late unknown results cannot rewrite it. The stored originator/workspace may reconcile after membership revocation so already-incurred costs are not lost; it cannot reserve fresh work after revocation. There is no public settlement endpoint.

If observed actual cost exceeds the declared maximum, record it instead of hiding/rejecting the bill, disable the underbounded profile and count the full amount against future admission. This is an accounting anomaly requiring operator price/bound review; it cannot undo an incurred charge. Profiles with unknown/unbounded pricing must never be enabled in the first place.

## Failure walkthrough and verification

Two US$0.60 requests compete for a US$1 workspace allocation: one reserves, one receives `workspace_limit`. Different workspaces also compete against the same US$20 ceiling. A US$0.60 operation with unknown execution continues to hold US$0.60. Later confirmed US$0.20 reconciliation releases US$0.40 once; a reload/replay retains the same operation rather than dispatching again. Lock-wait tests change membership, cap and profile status before admission resumes and verify no stale permission/capacity is granted.

Revision `0007_budget` adds three tables, private financial functions and immutable profile protection. Financial tables are RLS-enabled with no direct runtime read/write grant; profile/processor metadata is nonsecret and globally readable. Raw operation keys, content, credentials, global totals and another tenant's spending never appear in usage responses. Downgrading drops profiles, allowances and financial history and is not a data-preserving production rollback.

Only guarded disposable PostgreSQL is used for tests. Its fixture resets immutable profile/ledger records with a fixed-table TRUNCATE (no CASCADE), after checking the isolated database URL; this reset is not an application feature.

```powershell
docker compose --profile test up -d --wait test-db
uv run --project backend --locked --cache-dir backend/.uv-cache pytest backend/tests -q -W error --tb=short
docker compose --profile test stop test-db
```

Results and independent review are in the [budget plan](../superpowers/plans/2026-10-30-budget.md). No live prices, account availability, inference, frontend integration or persistent database migration is claimed. Next backend work is the small-corpus approved-source/document ingestion path, with explicit adapter/capability/price verification before hosted embedding or reranking.
