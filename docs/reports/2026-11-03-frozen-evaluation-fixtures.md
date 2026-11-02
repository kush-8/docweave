# Frozen evaluation sources and execution map

The current pending benchmark is [release-draft-v2.json](../../backend/eval/fixtures/release-draft-v2.json): 150 cases, 100 development/50 held-out candidates, 210 factual labels. Its SHA-256 is `cbc71c66de9a767ee8c5e5b6ac0398498f8556caeb7744477a296d327047c3d2`. The original v1 remains unchanged. Human label review is still pending.

All 29 exact references have raw-byte and normalized-text hashes, attribution, media types and application-parser snapshots in private `backups/release-sources-20261103-v4/`. The manifest binds the dataset and [minimal offline source registry](../../backend/eval/fixtures/release-sources-v2.json). This registry permits private benchmark capture only; the production catalog, source approval and processor consent were not changed. No publisher bodies are committed.

V2 replaces the SQLAlchemy and Playwright rendered references with their already registered, commit-pinned official source documents. The pgvector reference is its official README at commit `1d5ef0a160cadec08f754528669ce17e20eab38c`, resolved from the publisher repository. The RDS backup introduction was reviewed as one exact additional offline reference. These choices do not assert installed-package compatibility. RST roles/includes, links and dynamic content are not expanded.

`support-review-pending.json` in the private snapshot folder contains 210 character-exact candidate spans, selected by word overlap. **They are candidates, not verified semantic support.** The validator binds the manifest/dataset, checks source membership, fact indices, offsets and exact quotes, and rejects later mutations. Both reviewed labels and identified human span review are required before eligibility. Current eligibility is false. Human output reviews remain a later, separate requirement.

## Shared parser correction

Real AWS Markdown exposed a shared chunker loop: blank lines before the first heading produced a boundary before the first token, repeatedly adding the same chunk until the 10,000-chunk guard rejected the page. A tiny synthetic regression failed first. Boundary lookup now starts from the first content token while preserving original offsets. The isolated image was rebuilt from the existing pinned Dockerfile; its result must match the current host parser before freezing accepts a page. No parser bounds were relaxed.

The existing 85-page catalog verifier was rerun successfully with the corrected parser: 85/85 fetch/robots/parse checks, 798 chunks and 1,707,436 normalized characters. The tracked metadata report now binds current parser hashes. These counts remain bounded-reference evidence, not an embedding/index or release-quality result.

## Reusable execution fixtures

The complete backend run includes these existing executable fixtures. They establish infrastructure behavior with mocked provider HTTP; they do not count as execution of the 150 proposed questions.

| Release behavior | Existing executable fixture | Remaining case-specific setup |
| --- | --- | --- |
| Ordinary cited turn, follow-up, source wait and same-turn resume | `backend/tests/personal/test_personal_answer_pipeline.py::test_personal_question_runs_hybrid_rerank_and_validated_answer` | Provision each case's pinned corpus, project stack/version selection and history; bind captured job to case ID. |
| Long history, incremental/stale summary, context/policy fencing and deletion | `backend/tests/personal/test_summary_persistence.py::test_summary_persists_rebuilds_and_is_fenced_and_erased` | Add explicit multi-turn sequences to reviewed cases and distinguish fixture summary tests from live summary eligibility. |
| Upstream identity revocation and session removal | `backend/tests/github/test_github.py::test_concurrent_refresh_runs_once_and_identity_revocation_deletes_session` | Provision a revoked identity/access condition; capture HTTP denial rather than inventing a generated `blocked_policy` answer. |
| Exact-version/source review and stale proof rejection | `backend/tests/personal/test_personal_api.py::test_github_project_upload_and_exact_version_review` | Provision accepted versus unaccepted target coverage for each version control. |
| Retained private source requires current owner and exact version | `backend/tests/personal/test_guardrail_private_review.py::test_retained_private_review_is_exact_owner_bound_and_restore_fenced` | Provision both owners and exact retained citation/source identities for denial controls. |
| Final release under changed policy; idempotent response checks | `backend/tests/api/test_guardrail_http_release.py` | Execute the actual case query and record its guardrail outcome separately from answer abstention. |

`no_evidence` cases must have an actually empty eligible supporting scope or deliberately absent deployment facts; a question's claim that evidence is missing is not a fixture. Likewise, denial requires real access state and version controls require real selection/coverage state. Until those are provisioned and mapped, the benchmark is not executable end to end. Labels must not be fed to the model as context.

## Verification and next work

Full backend: **707 passed in 220.82 seconds**, warnings as errors; JUnit independently confirms zero failures/errors/skips (`logs/frozen-fixtures-final-20261103.xml`). Final snapshot/review/catalog selection:24 passed. Independent review found manifest-state/hash-binding issues that were corrected; re-review found no remaining actionable issues. The personal worker was safely drained/restarted to load the correction. No extra provider calls, private activation, schema migration or commit occurred in this phase.

Next: complete the case-specific access/version/history fixture runner, review/correct labels and candidate spans, then prepare the concrete paid-run budget. The full benchmark, its metrics and 30+30 human output reviews are not complete. Backup expiry/restore-deletion policy and summary/private activation also remain separate release work. The overall goal remains active.
