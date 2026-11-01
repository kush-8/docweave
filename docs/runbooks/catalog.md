# Documentation coverage and source review

Projects expose `GET /api/v1/projects/{project_id}/documentation`. The response binds coverage to `context_revision` and the configured `RAG_GENERATION_ID`; each dependency includes the available immutable revisions, actual exact/major/minor coverage, attribution, source URL, current state and safe worker stage. Missing coverage, operator approval, version approval, capacity, permanent failure and active preparation are distinct. An absent or disabled generation is capacity, not indexing progress.

The Project documentation panel lets the owner review sources and select coverage. `PUT /projects/{project_id}/documentation/{dependency_id}` requires current owner/upstream access, Origin, CSRF and `expected_revision`. Send `revision_id` to select an operator-approved matching source. Broader major/minor coverage also requires `accept_fallback: true`; acceptance binds that exact dependency documentation target and immutable catalog revision. A changed target requires new acceptance. Omit `revision_id` to remove the selection. Removal persists across automatic reconciliation for the same target and never deletes a shared index or another project's selection.

Choices increment project context only when they change. Stale or concurrently processing context returns 409; reload before deciding again. The worker reuses accepted choices, and retrieval, retained history and citation release check current selection, coverage, source approval and enabled generation. Changing a choice cannot authorize provider processing or replay a paid operation.

## Operator review

Ordinary project APIs cannot approve, mutate or publish public sources. Unknown public sources can be staged for operator review through a bounded JSON manifest. Review publisher ownership, release/version relationship, exact page scope, attribution/license and robots rules before approving it. A public URL or a package name does not establish authority. Keep private repository names, URLs, configs and credentials out of public manifests. This command performs no discovery lookups, source fetches, embedding or provider calls.

From the repository root, with the backend environment installed:

```powershell
$env:PYTHONPATH = (Resolve-Path backend/src).Path
uv run --project backend --locked python -m docweave.catalog --manifest backend/catalog/publisher-pages.json
uv run --project backend --locked python -m docweave.catalog --manifest backend/catalog/publisher-pages.json --apply
```

The first command validates the manifest and prints its normalized SHA256 review hash. The second, requiring `docweave_migrator`, stages enabled but unapproved candidate revisions. Their public metadata is visible for review; they cannot be selected or fetched automatically. After actual operator review, add `--approve-hash <exact-reviewed-hash>` to the apply command. That creates immutable approved replacement revisions and disables the corresponding staged candidates. Editing any manifest fact changes its hash. Repetition reuses live identical revisions; a replaced/revoked revision cannot be reactivated by repeating the old command. A new review needs a changed, newly reviewed manifest.

`--database-url-env NAME` selects a privately configured migration-role URL without putting credentials in command arguments. `--apply --revoke <revision-uuid>` fences a revision without deleting its shared artifacts. Publication alone queues no jobs and enables no provider. Subsequent authorized project selection/sync may enqueue deduplicated catalog work only for an enabled generation; existing profile/account/capacity/spending gates still apply.

Manifest `entries` contain `technology`, `ecosystem` (`python` or `javascript`), `docs_target`, `coverage` (`granularity` and `version`), optional `package_aliases`, `origin`, `path_prefix`, `source_url`, `attribution` and `source_hash` (SHA256 of the exact fetched bytes). Sources must use bounded HTTPS origin/path scopes without credentials, queries or traversal. The worker retains DNS/IP pinning, robots, redirect, response and parser restrictions. Changed bytes fail before parsing/embedding and require a new reviewed revision; approval never waives document guardrails.

## Coverage limits

`backend/catalog/publisher-pages.json` contains three verified release/commit-pinned publisher pages: HTTPX QuickStart 0.28.1, Pydantic Models 2.9.2 and Starlette Applications 0.41.0. Attribution explicitly limits them to those pages; embedded documentation directives/includes are not expanded. These are real bounded examples, not complete library manuals or full catalog acceptance. The manifest is shipped for review and is not automatically installed, approved or indexed.

The [required reference registry](../../backend/catalog/README.md) covers all 29 agreed technologies with 85 enumerated official pages. Each page has successful robots, bounded fetch and actual application-parser evidence: 798 chunks and 1,707,106 normalized characters, with only hashes/counts retained. `/api/v1/catalog/references` and Browse official reference coverage expose those topics and source links. Rolling references and source snapshots explicitly remain ineligible for automatic exact-package matching. They do not assert complete manuals, historical-release compatibility or an approved live index.

## Publisher discovery and private review

`POST /projects/{project_id}/documentation/{dependency_id}/discover` requires current ownership/upstream access, Origin/CSRF, `expected_revision` and explicit boolean `allow_public_lookup: true`. It sends only the validated package name and resolved version to PyPI or npm; it never forwards configs, goals, repository URLs, credentials or arbitrary user URLs. Authorization is refreshed after DNS and immediately before dispatch. Registry redirects are rejected. Returned publisher links are untrusted proposals; no document is fetched yet.

Each proposal has a ten-minute encrypted `candidate_token` bound to owner, project, dependency, target and context revision. Review the publisher page, then submit the token, current revision and actual exact/major/minor `coverage` to `POST .../review-source`. Broader coverage needs explicit `accept_fallback: true`. The source review and ingestion intent commit atomically. Approval stays private to the project and never creates or approves a public catalog revision. Stale proposals require fresh discovery. Removing private documentation also persists a target-bound exclusion and increments context, preventing later automatic public matching from undoing that choice.

Source imports accept bounded TXT, Markdown and static HTML. The isolated parser extracts visible main/article/body documentation, drops scripts/forms/navigation/hidden text, preserves offsets in the normalized snapshot, and enforces byte/text/node/depth limits. It never executes JavaScript, follows embedded links or expands documentation includes. JavaScript-only/unsupported pages fail explicitly. Original fetched bytes retain their own hash proof; parser/configuration and normalized content hashes identify searchable versions.

## Private indexing continuation

The personal worker periodically discovers eligible prepared private artifacts and deduplicates durable index jobs by document/version/generation. It reuses the shared indexer and existing provider admission. Fresh ownership, GitHub identity/repository access, source/stack facts, assessments, generation/profile/account/pricing, project/collection consent and budget checks precede hosted processing and publication. Completed recorded responses reuse their original reservation after reauthorization; uncertain results never replay automatically. Stale queue deliveries and expired leases resume the original job, and completion wakes original waiting turns.

Missing/disabled generation, absent consent, unavailable capacity, unknown completion and permanent failure remain distinct from active indexing. A source is ready only after eligible atomic index publication. Paid provider acceptance and full answer-quality evaluation remain separate release gates; no paid processing is enabled by source approval, migration or the reference registry. Readiness remains 503 until all release requirements pass.
