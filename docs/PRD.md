# DocWeave — Product Requirements

Status: Direction and GitHub extension confirmed on 2026-10-28. Folder scaffold initialized; application implementation has not started.

## Purpose and release outcome

DocWeave is a multi-tenant technical assistant for engineers delivering AI applications. A user creates a project, supplies its goal, optionally connects GitHub to detect its stack, reviews dependency/version facts and documentation sources, adds authorized private documents, and holds a persistent conversation with verifiable citations. Manual setup remains available.

The primary portfolio demonstration solves a concrete integration/troubleshooting problem using official documentation and private project knowledge. Learning is part of acceptance: the builder explains each milestone's choices and a relevant failure scenario. This is the full advanced Project 1, built independently of later portfolio applications.

The original [Enterprise Knowledge Intelligence brief](../../01_enterprise_knowledge_intelligence.md) supplies the broader requirements. This planning pack specializes it without requiring another portfolio application at runtime.

## Confirmed decisions

| Area | Required behavior |
| --- | --- |
| Runtime | Local Docker-based application and hosted model inference; real tenant isolation, not demo-only authentication |
| Tenancy | Workspace is the tenant; projects/collections belong to it; one identity may have separate memberships in several workspaces |
| Login | Google OAuth, GitHub OAuth, and verified email/password; verification, password reset, and secure account linking |
| Membership | Authenticated users may create a workspace as owner; existing workspaces require owner-issued, expiring, recipient-bound invitations |
| Authorization | Owner, maintainer, and member roles plus collection grants; all checks are server-side |
| Sources | All 29 catalog entries must have verified bounded coverage before the full release is complete |
| Imports | Project creation queues reviewed selected sources; verified catalog sources import automatically, while new origins and version fallbacks wait for approval |
| Versioning | Match detected/selected dependency versions to publisher-provided official versioned docs where available; record actual major/minor/exact coverage and captured snapshots |
| GitHub connection | Optional and separate from login; user-owned read-only access to selected repositories; private derived context also requires current upstream access |
| Stack detection | Static Python/JavaScript/TypeScript metadata only; one repo or monorepo application per project; review before importing |
| Dependency scope | Confirmed direct runtime dependencies preselected; development tools optional; unknown roles/directness require review; no automatic transitive-library documentation imports |
| Manifest support | requirements.txt, standard pyproject.toml, package.json declarations; uv.lock, package-lock.json, pnpm-lock.yaml resolved versions |
| Discovery fallback | Catalog first, then publisher-linked candidate sources; user source review before import, explicitly accepted major/minor fallback, unavailable state otherwise |
| Rescan | Manual; pin each scan to one commit and review dependency/version diffs before changing approved project context |
| Private knowledge | PDF, TXT, Markdown, DOCX; private processing requires approval for every actual external processor |
| Conversations | Persistent across reload/login/restart; private to their author and scoped to one project |
| Memory | Current project context, recent conversation, summarized older context, and relevant evidence; no arbitrary chat-length cutoff |
| Answer provider | Gemini, Groq, or Hugging Face hosted inference selected at conversation creation and fixed for that conversation |
| Retrieval | Gemini embeddings and bounded Gemini LLM reranking; lexical/vector search and documented fusion |
| Clarification | Ask a focused follow-up when essential information is missing; avoid asking for information already in context |
| Reliability | Accepted turns finish independently of the browser; recover status/results and prevent duplicate submissions |
| Access changes | Revoked/deleted remembered sources pause affected conversations; affected content and derived memory become inaccessible |
| Spending | Global US$20/month API ceiling plus operator-configured workspace caps; tenants see only their own usage |
| Frontend | Evidence-first workbench, private recent conversations, citation inspector, responsive UI, light/dark toggle |
| Retention | Conversations and referenced snapshots stay until explicit deletion; immediate access removal, 24-hour local cleanup, seven-day backup expiry, 90-day content-free audit records |
| Evaluation | 150 scenarios, including multi-turn behavior; 100 development/50 held-out; distinct 30-output development and release human reviews |
| Delivery | Complete vertical workflow first, then full catalog/providers/evaluation/operations |
| Change authority | Only the user can approve reductions to accepted scope or release criteria |

Cleanup deadlines assume services are running; overdue deletion runs before traffic is accepted after downtime. Local deletion cannot recall content already dispatched to a provider.

## User stories and acceptance

| ID | Story | Acceptance |
| --- | --- | --- |
| P1 | Sign in and manage tenant membership | All three login methods work; verified recipient accepts an invitation once; IDs alone grant no access |
| P2 | Create a project | Goal required; manual stack or reviewed GitHub detection; optional environment/architecture/constraints; approved imports durably queued |
| P3 | Maintain knowledge | Validate, scan where configured, parse, version, refresh, replace, re-index, and delete without losing a previous good version on failure |
| P4 | Converse with context | A follow-up resolves relevant earlier references and current project settings; users can resume private conversations after restart |
| P5 | Inspect an answer | Claims cite real retained source spans; project notes and prior assistant messages are not documentary proof |
| P6 | Handle missing information | Clarification, insufficient evidence, operational failure, paused access, and uncertain completion are distinct states |
| P7 | Enforce access and processing policy | Recheck membership, grants, source status, and processor approval before external calls and result/evidence release, including remembered material |
| P8 | Investigate and recover | Safe job/turn status, request IDs, stage timing, costs, retries, and recovery are available to authorized users |
| P9 | Compare configurations | Reproduce lexical/vector/hybrid/reranked retrieval and three answer-provider comparisons without contaminating held-out data |
| P10 | Connect and scan a repository | Explicit repository/branch/application selection, read-only metadata scan, coherent commit provenance, no execution or source-code ingestion |
| P11 | Review documentation choices | Separate declared constraint, resolved version/revision, selected docs version, and actual source coverage; unknown/private/unavailable cases remain explicit |
| P12 | Refresh or disconnect GitHub | Review rescan diff before applying; recheck upstream access for viewers/workers; pause affected private context on loss while manual projects remain usable |

## Scope and non-goals

Preserve durable jobs, content validation/limits, isolated parsers, content hashing/deduplication, structure-aware chunks, versioned index configurations, citations/abstention, audit, migrations, rate limits, CI, load/failure tests, telemetry, and tested backup/restore.

Initial document support is English and text-extractable PDF/TXT/Markdown/DOCX, plus the bounded repository metadata scan described above. OCR, spreadsheets/slides, application source-code ingestion, repository cloning/execution, unrestricted web discovery, autonomous browsing/tools, code execution, customer infrastructure deployment, commercial billing, and tenant-specific enterprise SSO are excluded. Other ecosystems and unsupported lockfiles use manual stack/version selection, not guessed resolution.

Provider choice means the inference service: **Groq is not Grok**. A Groq-served model may have another publisher without introducing that publisher's API. Hugging Face is hosted; local inference is not an automatic fallback.

The 29-entry registry remains the verified baseline. Outside it, bounded publisher-linked source discovery is supported, with project/workspace-scoped approval and visible version coverage. User approval does not promote a source into the globally verified catalog. Supplied URLs remain subject to official-source review, public-address/redirect validation, site restrictions, and quotas.

Unknown/private-index/local-path/Git dependencies stay out of public lookups unless explicitly approved. Never send raw repository configuration, credentials, or private repository URLs to discovery services. Retain normalized dependency facts and minimal redacted provenance; static detection does not prove deployment or active use.

## Future goals

Confirmed on 2026-10-29: introduce a DocWeave Model Context Protocol (MCP) server after the core application workflow is working and evaluated. Compatible assistants should be able to search authorized project knowledge and retrieve evidence with source citations through the same backend used by the web application.

Reuse backend retrieval and authorization, preserving tenant/project isolation, collection grants, current upstream access checks, source revocation/deletion, and applicable external-processing approvals. Define the MCP tool contracts, client authentication, and compatibility checks when this goal is scheduled. This is a future extension, not a current release requirement; it does not replace the web application or change the accepted release criteria. No MCP-specific infrastructure is needed now.

## Engineering defaults and verification boundaries

Approved stack direction: React/TypeScript, FastAPI, PostgreSQL/pgvector, LangGraph/LangChain, a PostgreSQL-backed durable worker, and Keycloak. [architecture.md](architecture.md) owns exact contracts, model candidates, numeric limits, security, evaluation, and operations. [design.md](design.md) owns frontend appearance and flow.

Model/backend IDs, adapter compatibility, actual prices, source manifests/permissions, reference hardware, rendered accessibility, quality, and latency require evidence. Public documentation is not proof that an account can use a model. No such runtime proof is claimed here.

## Full release evidence

- A clean setup demonstrates all login methods, two isolated tenants, invitations/roles/grants, manual and GitHub setup, reviewed/version-aware imports, private uploads, contextual multi-turn answers, citations, refresh, re-index, deletion, and recovery.
- Unauthorized data never reaches a provider, citation, conversation, checkpoint, summary, cache, or response; deterministic boundary tests prove this.
- All 29 entries pass bounded ingestion, locators, attribution/robots checks, and representative final answer/citation smoke tests. Separate integration cases prove noncatalog discovery/review, explicit version fallback, unresolved versions, monorepo isolation, malformed manifests, and upstream revocation; discovery does not guarantee docs exist for every package.
- Evaluation reports retrieval relevance, correctness, grounding, citation validity, clarification/abstention, memory continuity, latency, and cost with model/config/corpus versions.
- Calibrate on development data, freeze configurations/rubrics, then evaluate held-out scenarios. Human release review is separate from calibration.
- CI runs deterministic unit/database/security/browser/regression checks without paid keys; budget-reserved live checks are separate.
- Load/failure/restore drills and an honest portfolio demonstration include setup, architecture, threat model, OpenAPI usage, runbooks, measurements, limitations, and learning explanations.

## Document ownership

| File | Authority |
| --- | --- |
| [PRD.md](PRD.md) | Product intent, accepted scope, release outcomes |
| [architecture.md](architecture.md) | Components, data, APIs, system behavior, security, memory, budget, evaluation, operations |
| [design.md](design.md) | Frontend visuals, navigation, app flows, UI states, accessibility |
| [rules.md](rules.md) | Engineering/workflow constraints, approval authority, document maintenance |
| [tasks.md](tasks.md) | Ordered implementation tasks, interfaces, checks, learning evidence |
| [memory.md](memory.md) | Concise confirmed decisions, real progress, unresolved verification, next action |
