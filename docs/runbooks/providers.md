# Provider configuration

Groq is used for hosted query resolution, reranking, generation and planned summaries/judges. Gemini is the embedding exception. Use immutable operator-verified profiles and active index generation; current environment names are in [.env.example](../../.env.example). Configure `RAG_GENERATION_ID`, `EMBEDDING_PROFILE_ID`, `QUERY_PROFILE_ID`, `RERANK_PROFILE_ID` and optional default `ANSWER_PROFILE_ID` along with privately stored keys.

Profiles bind provider/model/backend/role/processor IDs, token/attempt bounds and price card. Enabled flags do not repoint identity. Verify actual account, capability, billing/prices and purpose eligibility before enabling. Do not send private content under a public/synthetic exception or billing-unknown/free configuration. Normal dispatch still checks owner/upstream access, source/assessment, consent and conservative global admission.

Use current integrations in `backend/src/docweave/integrations/` and admitted orchestration in `services/personal_providers.py`. All roles use bounded no-retry HTTP, provenance-separated structured prompts and validated responses. Completion_unknown cannot be automatically replayed. Tests replace HTTP and establish boundary behavior, not live provider eligibility or invoice costs.

[Spending](budget.md), [retrieval](retrieval.md), [personal setup](personal-projects.md) and [remaining verification](../tasks.md) contain the current operating requirements. Historical model/probe results and quoted prices are kept only in [memory](../memory.md); verify current external facts before any live run.
