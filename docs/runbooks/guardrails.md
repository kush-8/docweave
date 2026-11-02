# Guardrail lifecycle

Guardrail scanning runs locally through LangChain Core. Normalization and bounded deterministic credential/instruction checks form a `RunnableSequence`; the existing `assess_text` interface is used by ingestion, indexing, chat and generated-output checks. Scans disable tracing and never call a model. Finding records contain rule IDs, never matched credentials. Detection remains heuristic: passing a scan does not establish complete attack detection or semantic answer quality.

## Rules and deployment

The scanner revision hashes its rules, placeholders, normalization/detection implementation, Unicode version and scan bound. Database policy epochs advance monotonically to distinguish A→B→A changes. Assessment eligibility binds the exact document version, content hash, parser hash, scanner revision and epoch; injection approval also requires the current private owner or the public catalog operator marker.

Apply `0040_guardrail_lifecycle` only through the normal private backup, actual restore rehearsal and preservation checks. API/worker startup does not migrate. Deploy matching scanner code to API and workers; a worker compiled for different rules cannot dispatch or publish assessments. Use the operator commands from the configured backend source environment:

```powershell
python -m docweave.guardrails status
python -m docweave.guardrails activate --expected-epoch 1
python -m docweave.guardrails audit --limit 100
```

Commands use `MIGRATION_DATABASE_URL` and require the migration login. `status` returns the compiled and active revisions, current epoch and rescan counts. Every explicit activation advances the expected epoch, including unchanged rules, so the operator can fence a restored backup. Activation immediately holds older assessments and invalidates summaries. Private evidence releases fail closed when the restored database policy differs from the compiled scanner. Restore while services are stopped, activate the compiled policy before restarting them, then allow local rescans to finish. Activation grants no source, provider, spending or private-processing authority. Do not disable a check to work around a scanner/database mismatch.

## Rescans and recovery

The personal worker reconciles local rescan intents at startup and every ten seconds, in batches of 100. It covers all versions of undeleted documents, including older cited/indexed snapshots. Existing Procrastinate deliveries and application leases prevent duplicate publication; expired leases resume under a new token. Publication rechecks the epoch, exact hash/parser binding and live document. Missing, corrupt or oversized artifacts fail closed with a content-free audit event. Cancellation preserves the lease for recovery.

Clean current versions regain eligibility without refetching or reembedding compatible retained vectors. Flagged versions need a fresh exact-epoch review; prior approval cannot survive a rule change. Current source states distinguish active rescanning, review and failed rescans, preserving source-dependent turn intent. Rescan completion wakes existing waits, whose continuation still rechecks access, current context, consent and budget.

After restoring the exact private artifact, retry a failed local scan explicitly:

```powershell
python -m docweave.guardrails retry --version DOCUMENT_VERSION_UUID
```

This command never replays an embedding or language-model request. Do not delete financial claims or unknown-completion state during recovery. A downgrade refuses to discard lifecycle audit/rescan records.

## Review and audit

Private review requires current GitHub/project ownership and CSRF/Origin checks. `GET /documents/{id}/assessment` supplies the exact hash, rule revision, policy epoch, finding IDs and rescan state. Both assessment and review GET endpoints accept `document_version_id` to inspect a retained older snapshot; omitting it selects the active snapshot. Review pages are limited to 16,000 characters and verify the stored artifact before display. `POST /documents/{id}/review` requires `document_version_id`, `content_hash`, `rule_revision` and `policy_epoch`; a stale request fails. Credentials, incomplete scans and mismatched parser bindings cannot be waived. Replace over-bound content with a new bounded version rather than attempting to approve an incomplete scan.

Public injection examples require operator review; a personal API cannot approve shared content. Inspect the exact artifact and retain its displayed content hash/epoch before approving:

```powershell
python -m docweave.guardrails inspect --version DOCUMENT_VERSION_UUID --offset 0
python -m docweave.guardrails review --version DOCUMENT_VERSION_UUID --content-hash EXACT_SHA256 --expected-epoch CURRENT_EPOCH
```

Use `next_offset` to continue a bounded inspection. `audit --limit 100` returns safe activation, assessment, failed-scan, retry and review events; pass the last event ID with `--after` for the next page. Audit records bind version, rule revision, epoch and reviewer identity. Restrict console access when intentionally inspecting flagged content.

## Hosted processing and retained context

All admitted private stages validate inputs before reservation/HTTP, recheck policy/authority on continuation and reject blocked output before response checkpointing. Query/project/history fields are untrusted context; reviewed evidence stays data and never authorizes an action. Structured responses are validated in decoded form so JSON Unicode escapes cannot hide a credential. Incurred and uncertain charges survive rejected output; there is no automatic regeneration.

Citation release rechecks current assessment/source/selection/generation and private processor approvals. Compiled-policy fences run in the actual HTTP read transactions after upstream authorization. Completed historical turn text is checked under current rules even when it has no citations, including idempotent POST retries; blocked history cannot seed a summary. Saved summaries bind the policy epoch and authorized history; rule activation clears them and stale in-flight summaries cannot publish. Cached history is rechecked before each hosted stage. Prior answers and summaries never become documentary evidence. Fixed synthetic/public runners use the same local checks and policy fences; these exceptions never authorize private processing.

Full 150-scenario evaluation, human review, live-provider acceptance, cleanup/backup retention and development cutover remain separate operational gates; see [remaining work](../tasks.md).
