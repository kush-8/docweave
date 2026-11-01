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

All 29 agreed catalog entries still require verified bounded coverage before release. Publisher-linked discovery beyond operator-supplied manifests, project-private unknown-source review, broad catalog expansion and live indexed-corpus acceptance remain unfinished. Paid checks require separate authorization and archived accounting reconciliation. The grouped task in [tasks](../tasks.md) stays in progress until those requirements are met. Readiness remains 503.
