# Engineering rules

## Authority and scope

Read [PRD](PRD.md), [architecture](architecture.md), [tasks](tasks.md) and the [personal plan](superpowers/plans/2026-10-31-personal-github-projects.md). Current status belongs in the [report](reports/2026-11-01-personal-projects-checkpoint.md). History belongs only in [memory](memory.md); other docs describe current behavior and clearly marked pending requirements. Remove obsolete application code/tests instead of keeping duplicate runtimes. Keep migrations and actively required preservation/financial safeguards until safe cutover.

Keep changes small and complete across callers, tests, configuration and docs. Reuse existing layers/dependencies. Do not introduce pricing, workspace products, sharing, webhooks, repository-code ingestion or speculative infrastructure. Preserve concurrent work. No data reset, deployment, paid evaluation or automatic private processing is implied by implementation authorization.

## Boundaries

- SQL belongs in repositories/migrations, HTTP in routes/integrations, workflow decisions in services. Lower layers never import API/application composition. Validate at trust boundaries; use safe content-free errors/logs.
- Use verified GitHub numeric identity, never email matching. Check current user/App repository access; encrypt backend credentials and retain CSRF/Origin/cookie protections.
- Authorize private data by direct project owner. Public catalog mutation/review is operator-only; a private selection cannot publish public content. Recheck source/version/generation, consent, assessment and access at dispatch, continuation, publication and release.
- Never execute repository metadata. Pin all scan files to one resolved commit and bound trees/files/parsers. Preserve last good memory on partial scans. Unsupported formats must stay explicit.
- Preserve existing database/artifacts/IDs/hashes/vectors/ledger and unknown claims. Test only guarded disposable PostgreSQL (`127.0.0.1:55433/docweave_test`), serially. Rehearse development cutover on a restored copy before migration; never point tests at development.
- No automatic replay of paid completion_unknown. Conservative charge precedes HTTP, verified immutable profile/consent/budget gates remain, and rejected output does not erase cost.

## Structured prompt-writing rule

For generation, reranking, query resolution, summaries and offline judges, application-controlled task/rules/output contracts stay in verified supported trusted roles. Query, project context, conversation and evidence are JSON-serialized untrusted data with explicit empty categories. Do not interpolate content into trusted instructions. Preserve provenance and count framing/schema tokens; record prompt versions. Reviewed injection examples remain untrusted; credentials are never waived. Model output cannot authorize IO or create roles.

Validate structured claims, membership, exact spans/locators/version and current authority before history/checkpoint persistence and release. Invalid citations safely abstain; malformed output is operational failure; credentials/access violations block. No automatic regeneration of rejected output. Old assistant answers are not evidence. Rule/version/permission changes must invalidate dependent memory/citations; complete operational coverage remains pending in the [guardrail plan](superpowers/plans/2026-10-31-rag-guardrails.md).

## Verification

Nontrivial changes require focused meaningful tests, followed by appropriate suite checks. Keep deterministic mocks separate from live evidence. Preserve the full 150-scenario/100-development/50-held-out protocol and separate 30-output human reviews with the quality thresholds in [PRD](PRD.md). Report failures and denominators; do not claim release readiness from infrastructure or scanner unit tests. Live provider/GitHub setup, full evaluation and data cutover remain separate verification tasks.
