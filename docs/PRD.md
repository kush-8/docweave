# Product requirements

DocWeave is a personal GitHub-linked technical-documentation assistant and AI engineering showcase. A user owns projects, private knowledge and conversations. There are no workspaces, team roles, pricing tiers or sharing flows in the product.

## Core flow

1. Sign in using a GitHub App with read-only Contents/Metadata and selected repository access. Authorization is the intersection of the user's access and the App installation, including private repositories.
2. Create a project with a repository, short goal, branch and optional application folder. Default to the repository's default branch and root. Derive its name/stack; optional notes and constraints remain private. Existing bindings are immutable; an unbound preserved project can be linked once.
3. Starting a chat resolves branch HEAD and reads bounded supported dependency metadata at that commit. Never clone, execute code, install packages, embed repository source code or send raw configuration files to a model.
4. Preserve declared constraints, resolved versions and documentation coverage separately. Apply clear trusted changes automatically; incomplete/ambiguous scans retain last good memory and expose actionable states. Same-stack commits do not trigger new embeddings.
5. Match project dependencies against a shared public documentation catalog by ecosystem/technology and actual version coverage. Trusted exact matches can prepare automatically; unknown sources and version fallbacks require explicit review.
6. Retrieve private project knowledge plus selected eligible public indexes using hybrid lexical/vector search, RRF and reranking. Return inspectable, exact authorized citations. Existing chats use latest successful project memory on their next turn with a context-change notice.
7. Ingestion runs in the background. Only questions identified as depending on actively preparing sources wait. Resume the original durable turn once; distinguish missing coverage, approval, capacity, failure and cancellation from loading.

## Privacy, cost and safety

GitHub tokens and sessions stay server-side and encrypted. Private content is isolated by owner/project; shared catalog rows contain public documentation only. Recheck upstream access, scope, source/version, processing consent and guardrail eligibility before hosted processing, continuation and release. Credentials are nonwaivably blocked; reviewed injection examples remain untrusted evidence. Paid calls require verified immutable profiles and global spending admission. Never automatically replay uncertain paid completion.

Source-fetch allowlists, DNS pinning, no private network targets, strict parsers, structured prompts, exact citation validation and version-bound review remain required. Explicit deletion immediately fences use; live-data cleanup within 24 running-service hours and seven-day backup expiry are acceptance requirements still needing complete operational verification. Referenced snapshots persist until deletion and current access always gates citation reads.

## Completion criteria

The implemented core and its limitations are recorded in the [current report](reports/2026-11-01-personal-projects-checkpoint.md). Full release remains incomplete. The agreed evaluation includes 150 scenarios (100 development, 50 held-out), separate 30-output human reviews, Recall@10 >= 0.85, required-fact coverage >= 0.80, abstention recall >= 0.90, 100% structural citation validity and no severe unsupported operational/security claims or unauthorized disclosures. Report denominators, false positives, latency and cost; component tests do not establish semantic quality.

Semantic caching requires a later discussion. Webhooks, repository-code ingestion, public catalog administration UI, team sharing and established-project rebinding are omitted. See [remaining tasks](tasks.md), [architecture](architecture.md) and [guardrails](superpowers/plans/2026-10-31-rag-guardrails.md).
