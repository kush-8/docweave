# Release evaluation preparation

The [150-case draft](../../backend/eval/fixtures/release-draft-v1.json) is separate from the historical hash-pinned development pilot. It contains 100 development and 50 held-out candidates. Labels remain pending; the [source report](../reports/2026-11-03-release-dataset-draft.md) records coverage and limitations. Visible draft questions are not a sealed held-out result.

Before any full run, review the proposed factual labels, freeze the accepted official-source snapshots and exact supporting spans, provision the matching authorized project/source/version/access fixtures, and include executable multi-turn/context-change cases. The current draft does not supply those fixtures. Freeze the selected model/profile/generation/configuration before held-out execution. Expected answers and labels must never enter provider prompts. Do not reuse the Gemini-only historical pilot to claim evaluation of the selected OpenAI configuration.

`docweave.evaluation.personal.capture_personal_job` wraps the ordinary `run_personal_job` and `AnswerEngine` with the same GitHub, ownership, consent, guardrail, lease and spending checks. It accepts an already queued answer job and the existing engine/settings/client/configuration inputs. It records the production/migration/lock fingerprint, retrieval settings, request hashes, profile/model identities, reported usage, structured answer, final released turn and elapsed stage/job times. `retrieved_top_10` is the fused candidate list before reranking; final generation evidence still uses the normal eight-item cap. Failed or no-generation outcomes must be reviewed explicitly rather than inferred from answer prose. A completed job is not dispatched again by capture.

Captures are private operator data. Save them with the existing atomic `evaluation.reports.write_report` under ignored `backups/`, keyed by dataset case ID. Never put private captures, tokens or answers in the tracked fixture. Reported token usage is not a finalized invoice or proof of a new dispatch: a resumed stage can return its existing response. Obtain incurred/uncertain cost and reservation identity from the durable ledger, including rejected/unknown operations; do not sum reused usage as fresh spending.

After all 150 real authorized captures exist, prepare the two separate review packets without provider calls:

```powershell
$env:PYTHONPATH='backend/src;backend'
.\backend\.venv\Scripts\python.exe -m docweave.evaluation.release --dataset backend/eval/fixtures/release-draft-v1.json --captures backups/release-evaluation/captures.json --output backups/release-evaluation/reviews
```

The loader enforces exact split counts, unique IDs/questions, family separation, bounded files, source-reference shape and basic label consistency. These checks do not verify factual labels or grant source-fetch approval. Packet selection is deterministic; each split gets 30 outputs. Both packet hashes bind the complete dataset/capture inputs. Mutating loaded labels invalidates packet creation. Ratings remain empty and semantic-quality evidence remains false until actual human review and the full acceptance analysis are performed. Preserve both the reviewed artifact and its source bytes/hash; editing a label requires a newly reviewed artifact.

Human review must assess required-fact coverage, correctness, relevance, faithfulness, citation support, severe unsupported claims and disclosures. Supporting Recall@10 needs the frozen exact spans; source-URL presence alone is insufficient. Report abstention recall and false positives with explicit denominators, all structural citation checks, latency and retained/actual cost. Apply the [PRD thresholds](../PRD.md#completion-criteria) without tuning on held-out outputs.

The five fixed synthetic checks approved on 2026-11-03 are complete. They do not authorize this 150-scenario workload, indexing new corpora or live summaries. Prepare a concrete workload and conservative total before requesting its separate spending approval. Private processing remains disabled, and readiness stays 503. No acceptance switch is implemented while its required evidence is absent.
