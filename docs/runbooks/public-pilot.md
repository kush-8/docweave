# Public/synthetic evaluation tools

The frozen corpus and fixtures support reproducible operator-only retrieval/provider evaluation. Inputs are pinned by document/manifest/dataset hashes and retained licenses. Shared documentation/index reuse is separate from answer caching. Never substitute arbitrary private text into fixed public/synthetic authority.

Current source entry points are `evaluation/`, `evaluation/public_fixtures.py`, `services/public_pilot.py` and the compatibility/probe services. Inspect each CLI's help and current registration/profile requirements before running it. Recorded-vector evaluation can run without paid calls; hosted public/synthetic dispatch is explicitly budgeted, journaled and bounded. No new paid run is authorized by cleanup. Preserve failed reports and uncertain claims in private operator storage, without treating them as release quality evidence.

Tests in `backend/tests/evaluation/` and `backend/tests/providers/` check reproducibility, pinned input restrictions, current eligibility and conservative charges. Full held-out answer quality, human calibration, privacy, latency and cost acceptance remain in [tasks](../tasks.md). Historical measurements and decisions are in [memory](../memory.md), not this operating guide.
