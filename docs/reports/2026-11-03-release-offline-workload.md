# Complete offline release workload

The full pending-v3 workload ran against the actual 29-source frozen snapshot through authenticated HTTP submission/release, durable jobs, the ordinary answer engine and its provider admission/ledger path. All **150 cases plus six history turns (156 turns)** are captured in private `backups/release-offline-20261103-v1/`. Provider HTTP was intercepted; embeddings are synthetic 768-dimensional unit vectors and responses are deterministic fixtures. This establishes integration evidence, not semantic acceptance or real provider pricing.

| Observation | Result |
| --- | --- |
| Planned / captured turns | 156 / 156 |
| Admitted turns / submission denials | 154 / 2 |
| Released completed / policy-blocked turns | 152 / 2 |
| Intercepted requests / unique ledger reservations | 584 / 584 |
| Retained / unsettled / conservative fixture cost | US$0 / US$0 / US$0 |
| Full-workload replay | Same turn IDs; zero added requests or reservations |
| Unexpected HTTP or execution errors | 0 |

Completed is a durable turn status, not a correctness rating. The four SQLAlchemy cases remain present and source-blocked: `sqlalchemy-transaction-context`, `sqlalchemy-session-lifetime`, `sqlalchemy-task-concurrency`, and `sqlalchemy-flush-failure`. Their captures do not claim generated answers. Three no-evidence questions with public sources reach generation; the fake responder echoes documentation rather than performing semantic abstention. These outputs cannot pass an abstention-quality gate by virtue of this dry run.

Configuration was saved before execution. It pins the test generation/profile IDs, OpenAI `text-embedding-3-small`, Groq GPT-OSS20B resolution/reranking and GPT-OSS120B generation, BM25/exact retrieval, guardrail epoch1, implementation and fixture fingerprints. These disposable zero-price profiles are not live approved production profiles. The batch binds every case/history identity and query hash to the dataset and source manifest; aggregation verifies captured profiles, stages, implementation, generation, retrieval settings and ledger identities. Reservations are deduplicated across capture copies; replay is checked against the durable reservation count. Expected labels/outcomes and readable grader IDs are absent from intercepted requests.

The private archive contains configuration, captures, requests, physical provisioning identities, summary, the exact dataset/source snapshot, source/fixture fingerprint manifests, a code ZIP and passing JUnit evidence. `seal.json` binds their file hashes; its configuration/capture hashes use the evaluator's canonical representation. New capture runs refuse an existing output directory. Preserve this archive; use a new directory for any subsequent run, and invalidate this configuration if its bound inputs change.

| Binding | SHA-256 |
| --- | --- |
| Dataset | `14ac914538d574ebd027d832feac754cfaae74ef40298530fb48f69f9f417970` |
| Source manifest | `9dbfe803be2c31ba5aaa752e58041ca63e7ebf1eb64ec8a649012994643ff6dd` |
| Configuration | `552ffd9c4a07c4484bc25c0a6677e879cd46d909b20060f63ff5e52a08fb79fa` |
| Captures | `77080ed036762f6386ad6fee5a7343cd55dfcdf7a4d3ab625df79207bd05476a` |
| Archive seal | `6ae46f04d24f3cc686b9212b50c58e50ed6dae18f6b345d84485d3e2bca8caac` |

The actual-corpus full-run integration check passed in 264.04 seconds. The other 104 evaluation regressions passed in 125.92 seconds (only the already-passed full workload deselected); together they cover all 105 collected evaluation tests. The workload/cost subset also passed 23 tests in 1.11 seconds. All runs used warnings as errors; the preserved JUnit files have zero failures/errors/skips. Sealing recomputed the complete summary from serialized captures, checked current implementation/fixture fingerprints, verified every archived code member and read back every sealed file hash.

Paid budget/authority, eligible source curation, actual human label/span review, real quality/latency/cost measurements and the two separate 30-output human reviews remain open. `release_ready` and `semantic_quality_evidence` remain false. No paid calls, live processing activation, staging or commits were performed. Live runtime checks and the entire backend suite were outside this offline slice.
