# DocWeave — Architecture

Status: Confirmed direction and GitHub extension, reconciled 2026-10-28. Backend auth, workspaces, memberships/invitations, manual projects, collection grants and separate processor-consent policies are implemented. Documentation requests remain pending; budget admission, catalog approval/imports, GitHub setup and conversations remain incomplete. See [auth](runbooks/auth.md), [workspace](runbooks/workspaces.md), [membership](runbooks/memberships.md), [project](runbooks/projects.md) and [collection policy](runbooks/collection-policy.md) evidence.
Product: [PRD.md](PRD.md). Frontend: [design.md](design.md). Delivery: [tasks.md](tasks.md).
Numeric settings are explicit engineering defaults; quality/performance targets below require development baselining before release evaluation.

Physical folder boundaries are mapped in [README.md](../README.md). Backend-owned catalog manifests, evaluation data/reports, and service configuration live in `backend/catalog/`, `backend/eval/`, and `backend/infra/`. The folder scaffold exists; the runtime components below remain unimplemented.

## Approach and runtime

Use a bounded LangGraph workflow and LangChain integrations. An ordinary service pipeline was considered; the graph was selected to make state, memory, clarification, evidence validation, and failure paths inspectable. Keep one modular FastAPI backend with separate worker processes, rather than creating application microservices for every stage.

PostgreSQL owns metadata, application sessions, tenant policies, full-text/vector indexes, queue state, usage reservations, and persisted conversation checkpoints. Use pgvector rather than adding a separate vector database without a measured need. Qdrant/Redis/Terraform/AWS remain catalog knowledge, not required runtime services.

| Component | Choice and responsibility |
| --- | --- |
| UI | React, TypeScript, Vite; one browser origin with the API |
| API | FastAPI/Pydantic; identity/session, policy, domain/API operations |
| Database | PostgreSQL, pgvector, SQLAlchemy, Alembic; ordinary runtime roles cannot own migrations or bypass RLS |
| Workers | Procrastinate-backed ingestion and turn queues; bounded GitHub scan/discovery job kinds reuse ingestion infrastructure |
| Parser | Restricted container/supervisor; per-file subprocess, bounded resources, no secrets or external egress |
| Identity | Keycloak OIDC application; Google/GitHub brokers plus verified email/password |
| Providers | Gemini embedding/reranking; Gemini/Groq/HF answer adapters; no unrecorded automatic routing |
| Storage | Private named volume for uploads/normalized content/snapshots; generated internal paths |
| Observability | Safe structured logs and OpenTelemetry; local Prometheus/Grafana/Tempo compose profile |
| Development email | Local mail-capture SMTP for verification/reset tests; configured delivering SMTP for actual inboxes |
| Evaluation | Versioned dataset and report-producing CLI using the same authorized application services |

Compose uses Linux containers and localhost bindings for development. This does not weaken tenant authorization. Public hosting is a separate delivery request; cookie/TLS/origin settings must be reviewed before exposing the app. Keycloak has separate database credentials/schema. Only worker/API processes mount private storage.

## Identity, tenancy, and grants

Validate OIDC issuer, audience, state, nonce, PKCE, and tokens using a maintained OIDC client. Persist identity by validated issuer/subject, not email. Keep provider tokens server-side in expiring application sessions; HttpOnly, SameSite cookies and CSRF protection apply. Secure cookies/TLS are required except explicit localhost development configuration.

The backend auth slice uses Authlib, RS256 validation, encrypted PostgreSQL protocol/token records, hashed opaque session IDs, shared login throttling and exact-origin/session-bound CSRF. Sessions end at provider token expiry or eight hours; refresh/global IdP logout are not implemented. The actor can read only their own user row before membership; workspace/project reads still require current membership. Authentication creates no memberships. Local captured-email registration/verification/reset has separate live smoke evidence; real social-provider accounts and frontend auth integration remain deferred.

Google/GitHub login and email/password are all supported. Email verification/reset require SMTP. Callback URIs are exact and secrets server-side. Preserve identity-provider reauthentication/account-linking safeguards; an email-string match never merges accounts automatically. Magic links are not part of the chosen login method.

Workspace is the tenant. A user may create a workspace as owner and hold independent roles elsewhere. Existing-workspace membership comes from owner invitations: high-entropy hashed single-use token, 48-hour default expiry, intended verified recipient, atomic acceptance. Start with copyable invitation links rather than an invitation-email delivery product. Membership is never inferred from an email domain or a resource ID. Prevent removal/demotion of the last owner.

The backend creates a workspace and actor-owner membership atomically through a narrow runtime-only function, and lists current memberships with encrypted actor-bound keyset cursors. Actor-only context does not broaden ordinary tenant-table SELECTs. Workspace routes check current DB membership/required owner status. Member/invitation functions serialize on the workspace row and recheck authority after waiting; last-owner preservation, atomic single-use acceptance and current verified recipient checks are enforced there. Pending invitations are revoked when their issuing owner loses ownership. Collection RLS checks current membership plus ownership/grants, and role demotion/removal reconciles grants and revisions atomically. Owner-only grant/processor replacements share the workspace lock and optimistic revisions. Processor identity is immutable and operator-controlled; consent is independent by project/collection and does not enable hosted calls. No actor/role/email claim in a request grants authority. Frontend integration and downstream workers remain future work.

| Tenant role | Authority |
| --- | --- |
| Owner | Manage membership/roles, projects, collections/grants, and private processing approvals |
| Maintainer | Manage documents/sources in explicitly writable collections; cannot grant membership or processing consent |
| Member | Read explicitly readable collections and use their own authorized conversations |

Workspace membership allows ordinary manual-project context/navigation; private GitHub-derived labels/context additionally require upstream viewer eligibility. Collection contents/metadata remain grant-controlled. New collections start owner-only. Conversations and their titles/messages are author-private even from other project members/owners; an operator can manage infrastructure and safe metadata, not bypass application content policy. This is application isolation, not protection from a machine administrator who controls storage.

Use application query scoping plus PostgreSQL row-level policies on tenant-owned tables. Set tenant/actor context transaction-locally; pooled connections must not retain context. Worker operations reconstruct authority from current database state, not trusted job payload claims. Restrict queue/checkpoint schemas and functions to their dedicated service roles.

## Data model and version ownership

| Record | Important fields/relationships |
| --- | --- |
| User, Workspace, Membership, Invitation | Issuer/subject identity, workspace role, invitation recipient/hash/expiry/consumed state |
| Project, Collection, Grant | Workspace/project IDs, goal/stack/context revision, read/write grants, approved processors |
| CatalogEntry, DocumentationSelection, ProjectSource | Verified baseline plus project/workspace-approved origin/path/version selection and import status |
| GitHubConnection, RepositoryBinding, RepositoryScan | User-owned encrypted credentials, selected repo/branch/app scope, pinned commit/status/access evidence |
| DependencyFact, StackReview, SourceApproval | Source path/field/hash, declared constraint, locked version/revision/conditions, dependency role/directness, selected docs target/coverage, approval scope/revision |
| Document, DocumentVersion | Logical source, content hash, source locators, tombstone, active immutable version |
| IndexConfiguration, Chunk | Parser/chunker/model/revision/dimensions/normalization; vector/lexical data and exact source offsets |
| Conversation | Workspace, project, author, fixed answer profile, state, remembered source/approval dependencies |
| Turn, Citation | Ordered turn IDs, client idempotency key/request hash, status, validated result, pinned evidence references |
| Checkpoint, ConversationSummary | Conversation-owned graph state/writes, committed turn, summary provenance/dependencies; private persisted state |
| Job, InferenceOperation | Durable lease/attempt/stage; provider-call identity, reservation, dispatch/completion/uncertainty |
| BudgetPolicy, UsageReservation, UsageEvent | Operator workspace caps, global monthly ceiling, atomic reservation/reconciliation |
| AuditEvent | Actor, target IDs, action/outcome/request ID/time; no raw content |

All tenant-owned records include workspace ownership, including conversation/checkpoint state. Checkpointer thread/checkpoint IDs are lookup keys, not authorization. Keep checkpoint tables behind an application policy gateway; never expose generic graph-state endpoints.

Deduplicate same-workspace content/config only; do not disclose another tenant's hashes. Official docs are materialized per workspace initially. Preserve immutable snapshots used by citations. New retrieval uses active versions; authorized historical answers may read retained superseded snapshots. A normal refresh/re-index does not invalidate history.

## Public contracts

All resource routes below are under `/api/v1`. IDs are opaque. Lists use cursor pagination: default 25, maximum 100. Errors have stable code, safe message, and request ID. Mutations enforce sessions, CSRF, roles/grants, and resource ownership.

The [draft OpenAPI contract](../backend/openapi.yaml) and [API usage guide](api.md) make these families concrete. They document planned behavior, not implemented routes. The guide labels proposed wire decisions, including cookie/CSRF names, envelopes, revision guards, default collection creation, and explicit retry shapes. This architecture remains authoritative; reconcile differences before implementation.

| Route family | Contract |
| --- | --- |
| `/auth/login?method=email|google|github`, `/auth/callback`, `/auth/logout`, `/me` | OIDC lifecycle and actor; accepted method names are allowlisted |
| `/workspaces`, `/workspaces/{w}/members`, `/workspaces/{w}/invitations`, `/invitations/{token}/accept` | Create/select tenant, owner membership/invitation management |
| `/workspaces/{w}/projects`, `/projects/{p}` | Create/edit project; goal and selected stack required; automatic import jobs created durably |
| `/catalog`, `/providers` | Public supported-source definitions and configured/capable answer profiles; no keys |
| `/projects/{p}/collections`, `/collections/{id}/grants`, `/collections/{id}/processing-policy` | Collection access and owner processor approval |
| `/projects/{p}/sources`, `/sources/{id}/refresh` | Import reviewed DocumentationSelection records; refresh their bounded approved scope/version |
| `/connections/github/connect`, `/connections/github/callback`, `/connections/github` | Separate user-owned GitHub App authorization, safe connection status, disconnect |
| `/connections/github/repositories`, `/connections/github/repositories/{repo}/branches` | Only current actor/app-accessible choices; no global installation listing |
| `/repository-scans`, `/repository-scans/{scan}`, `/repository-scans/{scan}/review` | Bounded initial scan and explicit stack/version review before project creation |
| `/projects/{p}/repository/rescan`, `/projects/{p}/repository/apply` | Scan a new commit; review and apply its dependency/version diff |
| `/projects/{p}/documentation/discover`, `/projects/{p}/documentation/approve` | Approved identifier-only discovery; origin/path/version approval and import queuing |
| `/collections/{id}/documents`, `/documents/{id}/versions`, `/documents/{id}/reindex` | Upload/list/replace/delete, versions, re-index |
| `/jobs/{id}`, `/jobs/{id}/retry` | Authorized safe ingestion status/retry |
| `/projects/{p}/conversations`, `/conversations/{c}` | Create/list/read/delete author-private conversations; create input fixes provider profile |
| `/conversations/{c}/turns`, `/turns/{t}` | Append/list and recover turn status/result; append requires a client-generated idempotency key |
| `/turns/{t}/citations/{citation}` | Exact authorized captured span; no unavailable private metadata leaks |
| `/projects/{p}/usage`, `/workspaces/{w}/usage` | Own-tenant usage/allowance only; global spend is operator-only |

The draft also spells out lifecycle operations needed by these flows: project processing-policy read/replacement; member/invitation item mutations; source deletion; document metadata/replacement; project job listing; stored discovery candidate reads and user-proposed official-source candidates; scan-analysis deletion; and explicit `/turns/{t}/retry`. A retry after uncertain completion requires acknowledgement of possible prior charges and a new keyed intent/reservation. Candidate proposals create immutable review records, not fetch authority. These are draft API details within the accepted scope.

Project input: name, goal, manually selected technologies or a confirmed stack-review ID, and optional architecture notes/environment/constraints. A scan never invents the project goal. Creation returns project plus approved-source job IDs; project/import insertion is transactional or uses a transactional outbox. Unknown origins, unresolved versions, private lookups, and unaccepted version fallbacks remain pending review rather than bypassing the import gate. No configured budget/provider capacity produces a visible waiting state, not an unauthorized hosted call.

Conversation input: project, fixed answer profile, optional readable collection selection. Turn input: message and idempotency key; server supplies current project revision, authorized source scope, and committed conversation history. Same key/body returns the existing turn; same key/different body is a conflict. Allow one active turn per conversation.

Appending a turn returns HTTP 202 and a turn/status reference. Execution states: `queued`, `running`, `completed`, `failed`, `completion_unknown`, `blocked_policy`. A completed result kind is `answered`, `needs_clarification`, or `abstained`. Store validated text, citations, pinned versions/context revision, provider/model/backend identity, request ID, timing, and estimated/metered usage. Clarification is a conversation turn, not a hidden repeated model loop.

## GitHub connection and repository analysis

### Connection and upstream policy

GitHub is optional; manual stack selection and document uploads remain complete paths. Repository connection is separate from Keycloak GitHub sign-in. Use a GitHub App with repository Contents read access and required metadata, no writes; installation selects repositories. GitHub's permission can read contents broadly within those repositories. DocWeave's manifest/config/lockfile fetch allowlist is an application-enforced restriction, not a GitHub filename-scoped grant.

The connection belongs to the individual user and is bound explicitly to their authenticated DocWeave identity, independently of their login method. Use current user-on-behalf-of-App access for private scans/reads, intersected with installation/repository access. Organization policy/SSO/install approval may block connection; show an actionable safe status. Encrypt access/refresh credentials server-side; never place them in jobs, URLs, logs, or model prompts.

Every private repo-derived view, scan, application context, model-bound history/summary, and citation-like provenance view requires current DocWeave rights and upstream viewer/actor rights. A workspace owner cannot grant GitHub access. A colleague must connect their own eligible GitHub identity. Do not disclose private repository names/paths/stack facts via project lists, errors, telemetry, or cached UI to ineligible members.

Before displaying or using private repo-derived data, verify upstream eligibility; inability to verify fails closed with a temporary unavailable state. Disconnect/revocation/repository removal stops that user's affected processing/access and pauses dependent conversations. Delete local credentials immediately on disconnect; retain inaccessible extracted artifacts only under the explicit retention policy/provider requirements, and delete on request using the existing cleanup journal. Other users with independently valid connections are not automatically disconnected.

### Scan scope, provenance, and resource limits

One DocWeave project initially binds to one repository or selected monorepo application. Offer a branch selector defaulting to the repository default branch. Resolve it once to an immutable commit SHA; enumerate/fetch every file at that SHA. Preserve application paths and avoid mixing unrelated workspace applications or versions.

Use tree metadata to locate allowlisted files; skip symlinks/submodules/LFS pointers and generated/vendor/node_modules/.git trees. Fetch only recognized dependency/config data for the selected application plus explicitly identified enclosing workspace manifests/lockfiles and supported repository-local requirement includes. Keep outside-scope includes visible as incomplete rather than silently traversing arbitrary paths. Never clone, run/install packages, evaluate configuration code, follow external requirement includes, use private registry credentials, or retrieve .env/secret files.

Initial limits: at most 20,000 inspected tree entries, depth eight, 100 fetched metadata files, two MiB/file, ten MiB aggregate fetched bytes, and 200 GitHub requests per scan. These are application defaults below provider limits; API truncation and caps produce partial scan status. Do not treat a partial scan as a complete stack.

Parse fetched bytes transiently and discard them after extraction. Persist normalized selected dependency facts, minimal redacted field/path provenance, content hash, conditions, dependency group, commit, and scan/version metadata. Strip credentials, private URLs, and unrelated config values before storage; never forward raw configs to an LLM/discovery service. Original GitHub links still require independent upstream access. Dependency facts establish declarations/resolution at a commit, not active use or deployed versions.

### Initial parser contract

| Input | Supported interpretation |
| --- | --- |
| requirements.txt / explicitly scoped local includes | PEP 508 declarations/extras/markers and constraints; bounded path/cycle checks; role/directness unknown unless independently established/user-confirmed; constraint-only entries are not selected dependencies; exact pins are declarations, not proof of an installed environment |
| Standard pyproject.toml | project dependencies, optional groups, requires-python; retain dynamic/incomplete flags; no build backend execution |
| uv.lock | supported schema versions, locked candidates and conditions tied to selected project; preserve multiple-environment ambiguity |
| package.json | direct dependencies, optional/peer/dev roles and workspace identity; aliases/ranges/tags/URLs distinguished |
| package-lock.json | supported lockfile schema versions and selected workspace's resolved package entries |
| pnpm-lock.yaml | safe bounded YAML, supported lockfile schema/importer mapping and selected application's resolution |
| Other tool/config/lockfiles | detect unsupported/incomplete status; known-format adapters only, no generic config.toml dependency assumption |

Preselect only dependencies whose direct/runtime role is established by supported root metadata or user confirmation. Requirements files, frozen package lists, and standalone lock entries may not establish either: retain explicit unknown role/directness and require selection in review. Constraint-only entries constrain existing declarations; they never create a selected documentation dependency. Development tools are visible/optional; transitive-only dependencies do not trigger imports by default. Keep declarations, exact lockfile resolutions, VCS revisions, and user overrides separate. An exact declaration can supply a labeled declared docs target; it is not a lockfile or installed-version claim. Do not infer a release number from a Git commit or execute resolution. Surface manifest/lock mismatch and unsupported schema. Without a target environment, retain and label conditions rather than guessing which applies.

StackReview displays package/ecosystem/role, file/field, declared constraint, resolved version/revision where available, uncertainty, and intended docs target. The user corrects/confirms it before imports. Unsupported ecosystems remain manual. Unresolved or multiple candidates require an explicit docs version selection; that selection is not relabeled as a detected installed version.

### Version-aware documentation discovery

A DocumentationSelection records package/technology, declared/resolved dependency version, selected docs version, actual publisher granularity/range, origin/path/seed scope, source evidence, approval revision, and import status. Deduplicate by package plus approved version/scope within the workspace, not by package alone.

Resolution order: verified catalog and its supported official version routes -> approved public package/release registry metadata -> publisher-linked candidate docs/homepage/repository information -> user-supplied official URL/document when necessary. PyPI/npm metadata is publisher-supplied evidence, not independent domain-ownership or version proof. Display candidate versus globally verified source status honestly.

Use fixed allowlisted registry endpoints with encoded package identifiers. Before any public lookup of a private-index/local/Git/URL/unresolved dependency, obtain explicit identifier-only lookup consent in addition to applicable project processing policy. No private repo URLs, credentials, raw configs, or package artifacts leave through discovery. A denial simply leaves the dependency unresolved/manual.

Catalog selections with known version coverage auto-import after stack review. Noncatalog origin/path scopes require a one-time project/workspace approval before content fetch/import; batch review in setup. Approval does not override SSRF/redirect/public-address checks, robots/license restrictions, source limits, budgets, or current actor rights. User-approved sources do not modify the globally verified catalog; operator review/promotion is separate.

Prefer the most specific publisher-provided matching documentation. When exact docs are unavailable, present major/minor coverage and request explicit acceptance. Never silently substitute latest or claim exact patch coverage. Without a suitable source, return unavailable and offer a reviewed official URL/upload. Unsupported extraction formats remain visible failures, not inferred answers from model memory.

Apply the existing 100-page/source and 1,000-page/project ceilings across catalog and discovered sources. Process public metadata discovery in batches of at most 20 approved package identifiers, with at most three candidate origins/package and bounded metadata responses. Reuse durable ingestion jobs; there is no autonomous browsing tool in the answer graph.

### Rescan, diff, and conversations

Initial setup performs a commit-pinned scan, stack/version review, and goal entry before project creation. Creation queues approved catalog/version selections; project-scoped discovery and new-origin/fallback review then complete within setup/Sources. Pending external origins/version fallbacks stay pending while approved sources proceed; the discovery APIs do not require a nonexistent project.

Rescans are manual. Compare accepted versus candidate dependency facts and show additions/removals/role/version/condition changes with commit provenance. Apply only an explicitly reviewed diff; do not mutate approved project context merely because a branch changed. The next turn then uses the new project/scan revision with a visible update notice. Existing authorized historical citations keep their pinned snapshots; incompatible old docs stay out of new version-scoped retrieval.

No push-triggered autosync or external webhook relay is required initially. Current access checks before private views/inference remain mandatory regardless of rescan timing. Any future webhook path requires its own reachable receiver/signature/reconciliation design.

## Conversation context and memory

Persistent short-term memory is scoped to one conversation, author, project, and tenant. No cross-conversation or cross-project memory store is introduced. Capture current approved project context and authorized source/version choices at each turn's start; later project edits apply to the next turn and are visible in history metadata. For GitHub projects, this is the last accepted scan revision/commit, not an assertion about an unreviewed current branch or deployed environment. Upstream repo eligibility is an additional precondition for private repo-derived context, including summaries/checkpoints.

Keep the complete authorized transcript until explicit deletion. Bound model input rather than chat length. Initial answer-call allocation, in the selected model's tokenizer:

| Input category | Maximum tokens |
| --- | ---: |
| Older-history summary plus recent turns | 12,000 |
| Retrieved answer evidence | 6,000 |
| Project goal/stack/optional constraints | 2,000 |
| Current message | 2,000 |
| System instructions | 1,000 |
| Message/schema/source framing | 1,000 |
| **Total input ceiling** | **24,000** |

Reserve up to 1,200 total billed output tokens, including any reasoning. This is not a guarantee of 1,200 visible tokens; verify output-limit behavior per profile. Overlong current messages/project fields produce an actionable validation/context-limit response rather than silent truncation.

When history would exceed 12,000 tokens, summarize the oldest committed turns into at most 2,000 tokens and retain recent complete turns within the remaining allowance. Summary calls use the conversation's fixed approved answer provider, have their own bounded input/output reservation, and preserve decisions, unresolved questions, source references, and context revisions. Process older history in bounded batches; do not send the entire unlimited transcript to a summarizer.

Summaries are lossy context, not evidence or authority. Keep raw messages readable; disclose condensed context and ask clarification when needed. If mandatory constraints cannot fit, return an explicit context-limit/clarification result; there is no arbitrary maximum number of turns. Do not silently drop a mandatory project constraint or overwrite a newer user decision with an older summary.

Resolve ambiguous follow-up references against authorized conversation/project context before retrieval. This is required conversational query resolution, not speculative search optimization. Preserve the original message; construct a bounded retrieval query (maximum 1,024 embedding-model tokens) and clarify unresolved ambiguity. Never embed the entire conversation prompt. Optional additional query-rewriting experiments still need development evidence.

## Bounded retrieval and answering

Graph: authorize/revalidate -> load current context/history -> summarize if needed -> resolve query or clarify -> retrieve -> rerank -> build context -> generate -> validate -> persist/finalize. Every provider-bound step uses ordinary server policy and budget code; the model has no browser, shell, deployment, or policy-changing tools.

- Apply workspace/project/collection/processor grants, technology selection, active version, and tombstones in both lexical and vector queries before any candidate leaves the database.
- Retrieve up to 30 candidates/channel; deduplicate by chunk; reciprocal-rank fusion `k=60`; send the best 20 to Gemini listwise LLM reranking. PostgreSQL native full-text ranking is the lexical baseline, not BM25.
- Chunking starts at 350 tokens with 50-token fallback overlap, preserving headings/code/locators. Respect actual embedding-model limits; fail rather than silently truncate.
- Embedding candidate: Gemini Embedding 2, 768 dimensions and normalized vectors; changing model/dimensions/chunking creates a new index generation. Its tokenizer/input limit is separate from chat limits.
- Reranking is a separate Gemini request: up to 12,000 input/512 billed output tokens, containing the resolved query and at most 20 bounded passages/IDs. Do not apply the final 6,000-token evidence allowance to all 20 candidates. Validate returned IDs/order, duplicates, count, schema, grants, and source state. Generated relevance labels are not calibrated confidence.
- Retain up to eight reranked chunks within the answer evidence allowance. Calibrate relevance/abstention on development data.
- Generate structured claims/citation references or clarification/abstention. Schema-validate native structured output or parsed JSON; no unbounded repair loop.
- Validate citation membership, exact span/quote, retained version, current access, and source status. Structural citation validity does not prove semantic truth; evaluate correctness/grounding separately.
- Prior assistant messages, summaries, project descriptions, and proposed integration steps are not documentary proof. Fresh retrieval grounds new factual claims. Expose conflicts/version gaps instead of inventing unsupported facts.

Respect DocumentationSelection version scope in retrieval: package/version constraints, user-selected docs target, actual publisher coverage, and source snapshot are separate fields. Do not blend incompatible major/minor docs merely because package names match. Repository dependency facts are project context with provenance, not proof that an API behaves as documented or that a dependency is deployed.

The answer provider is fixed for a conversation. Starting a conversation with another provider starts fresh memory. No silent provider fallback. Freeze retrieval/reranking for generation comparisons.

## Privacy, revocation, and deletion

Owner approvals cover every external processor that will see private project context/documents/history. Gemini approval is required for private embeddings/reranking even when the answer provider is Groq/HF. Resolve the actual HF backend, not only the HF brand. User-authored messages sent through a chosen conversation are private application data and are covered by its project processing policy.

Revalidate before each external call and final result/evidence release, including after queue waits. For private GitHub-derived context, also verify the actor's current repo access through the user/App access intersection; workspace grants and installation tokens alone are insufficient. Preserve the provenance and policy dependencies of messages, summaries, checkpoints, and citations. A deleted/revoked source must not reappear through remembered assistant text.

When a remembered dependency becomes inaccessible, pause the affected conversation, hide affected content/derived memory, and offer a fresh conversation using current authorized knowledge. Do not automatically copy contaminated history into the new thread. Recovery after restored grants must revalidate all dependencies; deletion is not undone by restoring a checkpoint.

Explicit deletion immediately tombstones data and removes access. Erase affected live bytes/chunks, messages/derived summaries, checkpoints and intermediate writes within 24 hours of running service time; backups expire within seven days. Retain conversations and referenced snapshots otherwise until explicit deletion. Remove unreferenced superseded snapshots only through explicit maintenance; no hidden expiry of a referenced answer.

Keep content-free audit records for 90 days, operational logs/traces for seven days, and aggregated metrics for 30 days. Encryption/access keys are managed outside repository/backups. Restores apply the durable deletion/tombstone journal and current revocations before serving traffic; the journal survives until every pre-deletion backup expires. On startup, process overdue deletion before accepting requests. Already-viewed/copied data and dispatched provider requests cannot be recalled; document provider retention separately.

## Durable ingestion and turn execution

Upload bytes are validated into quarantine before any external processing; missing approvals produce `awaiting_approval`, not an inference call. Create document/job/outbox state transactionally. Jobs checkpoint identifiers/artifact state, not secret content in payloads. Repository scan/discovery jobs also reconstruct current actor, workspace, repo, and lookup-approval authority before processing.

Normalize/hash, parse, chunk, embed in bounded batches, stage a new version/index, then atomically publish after rechecking tombstones/config/policy. Same source/hash/config is idempotent. A failed refresh/replacement keeps the last good version and marks stale/partial coverage. A confirmed upstream removal retires it from new retrieval while preserving authorized cited snapshots.

Worker leases/heartbeats expire before reclaim; checkpoints/uniqueness protect duplicate delivery. Validation/policy failures do not retry; transient ingestion failures get at most three total attempts. External inference operations use dispatch records: a crash after dispatch without confirmed completion becomes `completion_unknown`, never an automatic paid replay. A user-confirmed retry gets a new reservation/attempt. Provider SDK retries are disabled; any safe application retry is accounted and bounded.

Use separate ingestion and turn queues. One active ingestion job; up to five active turns application-wide, two/user, one/conversation; default turn admission rate 10/minute/user. A turn has a 120-second worker deadline and individual external requests have 30-second timeouts. These are service limits, not a browser request timeout. Queue capacity/budget failures are explicit. User navigation never implicitly cancels or repeats a turn.

## Parsing and source fetch limits

The parser runs non-root with a read-only root filesystem, bounded tmpfs, dropped capabilities, no private persistent storage mount, no database/provider secrets, and only an internal worker/parser network. A trusted supervisor launches one short-lived subprocess per file with resource/time limits. Resource limits reduce blast radius; no claim of universal kernel-exploit resistance.

Default limits: 20 MiB/file, two million extracted characters, 500 PDF pages, 60-second parse, 512 MiB parser memory. Precheck DOCX archive entry/decompressed-byte limits. Reject encrypted/scanned-without-text/unsupported/oversized files with safe errors. OCR is excluded. Integrate ClamAV when configured; scanner failure quarantines, and disabled scanning is explicitly visible.

Documentation fetch authority is either a verified catalog manifest or an immutable project/workspace-approved DocumentationSelection/SourceApproval defining exact origin/path scope. Check that authority at dispatch and publication, including every redirect and connection-resolved address. Reject credentials, nonstandard ports, private/loopback/link-local/reserved addresses, non-HTTP(S), and DNS rebinding. Honor site/robots/attribution restrictions; a sitemap or llms.txt does not expand authority. Registry metadata and GitHub connector requests use their separately allowlisted API scopes. Documentation/registry HTTP clients never inherit GitHub tokens, cookies, or cross-origin authorization headers.

Limits: 100 accepted pages/entry, 1,000/project, two MiB decompressed/response, depth three, ten seconds/request, one request/second/host, and 200 total discovery/fetch attempts/entry. Fairly allocate the project ceiling among selected entries; show partial coverage at caps. Exclude login/download/language-duplicate/out-of-scope pages. Canonicalize URLs and keep exact locators/version declarations/capture time. Shared-host LangChain/LangGraph content deduplicates per workspace.

## Budget, models, and telemetry

Global API ceiling: US$20/month, Asia/Calcutta calendar boundaries; store timestamps in UTC. Operator-configured workspace caps must be set before hosted work. New workspaces wait for a configured allowance; project/import creation remains durable and visibly waits for budget. Caps are limits, not a promise of reserved global capacity. Workspace users see only their own usage/allowance; operator-only tooling sees global totals. No commercial billing UI.

Before every hosted batch/call—including probes, query resolution, summaries, embedding, reranking, generation, and automated judging—atomically reserve conservative maximum cost against both workspace and global balances. Include framing, billed reasoning/output, retry allowances, and provider fees. Reconcile confirmed usage; retain conservative charges for uncertain execution. Missing/unbounded pricing disables that profile. Do not provision idle-billed HF endpoints or rely on free credits.

Candidate generation profiles from public research, not verified account access:

| Role | Initial candidate |
| --- | --- |
| Default Gemini generation/reranking | `gemini-3.5-flash-lite` |
| Groq alternative | `openai/gpt-oss-20b`, served by Groq |
| HF alternative | `Qwen/Qwen3-8B` with explicitly pinned `nscale` backend |
| Embeddings | `gemini-embedding-2`, 768 dimensions |

Pin exact API/SDK versions, model/backend IDs, tokenizers, output/structured capabilities, and price cards after account-compatible, budget-reserved synthetic probes. Public metadata may select candidates before implementation; it cannot prove availability. Build/test the reservation boundary with fake providers before any probe. A replacement must stay within approved provider/feature/budget boundaries and be recorded; unsupported profile/scope changes return to the user.

No HF-hosted embedding/cross-encoder is required: the approved replacement is token-priced Gemini embedding plus LLM reranking. It changes ranking semantics, latency, and prompt sensitivity; evaluate it rather than claiming cross-encoder behavior.

Log actor/resource/request/job IDs, stage timings, outcomes, provider/model/config identity, and usage. Do not log prompts, source text, answers, summaries, tokens/cookies/headers/secrets. Dashboards cover ingestion, retrieval/turn latency, errors, tokens/cost, budget status, and queue recovery; alerts flag repeated failures, provider spikes, and budget thresholds.

Initial performance targets: local retrieval/fusion p95 under one second at 10,000 chunks; complete turn p95 under 20 seconds at one active turn. Measure five-turn load and summarization effects separately on a recorded machine/corpus. Targets are unmeasured, not guarantees.

## Evaluation and release protocol

Freeze 150 scenario IDs/families, labels, corpus snapshots, and the split before tuning. Scenario is the unit; multi-turn scenarios have explicit ordered turns and per-turn evidence/expected facts, so report both scenario and turn counts.

| Category | Development | Held-out | Total |
| --- | ---: | ---: | ---: |
| Single technology | 27 | 13 | 40 |
| Cross technology | 17 | 8 | 25 |
| Multi-turn context/summary | 16 | 9 | 25 |
| Unanswerable | 13 | 7 | 20 |
| Version/staleness/conflict | 10 | 5 | 15 |
| Permission/deletion | 10 | 5 | 15 |
| Adversarial documents | 7 | 3 | 10 |
| **Total** | **100** | **50** | **150** |

Include at least one development smoke scenario for each of the 29 entries. Keep representative GitHub-derived follow-ups/version conflicts within the 150 scenarios, and add deterministic connector/parser/discovery/security cases outside the scored benchmark; these do not require expanding the agreed human-review samples. Keep paraphrase/follow-up families together; do not leak held-out variants into tuning. Synthetic private fixtures are labeled as synthetic.

Compare lexical-only, vector-only, fused hybrid, and hybrid plus Gemini LLM reranking on identical snapshots/query representations. Report Recall@10, MRR@10, and nDCG@10 only when labels support them. Evaluate required facts, unsupported claims, grounding, citation validity, clarification/abstention, remembered decisions, summary continuity, cross-thread isolation, current project context, and revocation.

Choose 30 shared provider-comparison scenarios from development; give all three answer models identical authorized evidence/history and budgets. Human review 30 development outputs to calibrate judges; choose a separate stratified 30-output release sample from held-out results. Freeze models/prompts/reranking/rubrics before the held-out run. Human verification of labels and outputs is separate work; do not count one review twice.

Initial release targets: held-out Recall@10 >=0.85, required-fact coverage >=0.80 on answerable cases, abstention recall >=0.90 on unanswerable cases, 100% structural citation validity, and zero severe unsupported operational/security claims in human release review. Security tests allow zero unauthorized content in responses, inference, memory, checkpoints, or citations. Publish denominators and measured failures; any reduction to approved scope/criteria needs the user's explicit agreement.

If held-out results inform changes, those cases become development evidence; use fresh held-out cases for a new independent claim. CI uses deterministic recorded/fake-provider regression, not paid quality claims. Manually run budget-reserved live suites and publish the last run date. Baseline workload/cost estimates must include actual multi-turn, summary, reranking, judging, retry, and re-index counts; a token-price quote is not a measured release bill.

## Supported documentation catalog

Approved release catalog: **29 entries**. Docker includes Compose. These are coverage targets; each remains `planned` until its bounded import, attribution/robots checks, source locators, and final answer/citation smoke tests pass. Every entry uses the same Markdown/HTML ingestion path with registry data, not a bespoke crawler by default.

| Group | Entry | Official root and bounded subject area |
| --- | --- | --- |
| Language | Python | https://docs.python.org/3/ — tutorial, asyncio, relevant standard-library HTTP/concurrency sections |
| Language | TypeScript | https://www.typescriptlang.org/docs/ — handbook and project configuration |
| Frontend | React | https://react.dev/ — Learn and selected hook references |
| Frontend | Next.js | https://nextjs.org/docs/ — App Router fundamentals and server/client boundaries |
| Frontend | Tailwind CSS | https://tailwindcss.com/docs/ — setup, styling, layout, responsive design |
| Backend | FastAPI | https://fastapi.tiangolo.com/ — tutorial, security, dependencies, deployment |
| Backend | Pydantic | https://docs.pydantic.dev/latest/ — models, validation, settings references |
| Backend | SQLAlchemy | https://docs.sqlalchemy.org/en/20/ — ORM basics, sessions, transactions |
| AI | LangChain | https://docs.langchain.com/oss/python/langchain/ — models, retrieval, structured output |
| AI | LangGraph | https://docs.langchain.com/oss/python/langgraph/ — graphs, state, persistence, workflow patterns |
| AI | Hugging Face | https://huggingface.co/docs/transformers/ and https://huggingface.co/docs/inference-providers/ — inference, tokenization, hosted tasks |
| AI | vLLM | https://docs.vllm.ai/en/latest/ — serving, compatibility, deployment fundamentals |
| Data | PostgreSQL | https://www.postgresql.org/docs/current/ — SQL, indexes, transactions, full-text search, row security |
| Retrieval | pgvector | https://github.com/pgvector/pgvector — README and explicitly pinned official source documents |
| Retrieval | Qdrant | https://qdrant.tech/documentation/ — collections, filtering, search |
| Data | Redis | https://redis.io/docs/latest/ — data types, caching, streams fundamentals |
| Delivery | Docker / Compose | https://docs.docker.com/ — Dockerfile, networking, volumes, Compose |
| Delivery | GitHub Actions | https://docs.github.com/en/actions/ — workflows, secrets, permissions |
| Delivery | Terraform | https://developer.hashicorp.com/terraform/docs/ — language, state, workflow |
| AWS | S3 | https://docs.aws.amazon.com/AmazonS3/latest/userguide/ — objects, access, encryption |
| AWS | IAM | https://docs.aws.amazon.com/IAM/latest/UserGuide/ — identities, policies, least privilege |
| AWS | ECS | https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ — task definitions, services, deployment |
| AWS | RDS | https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/ — PostgreSQL connectivity, backup, operations |
| Observability | OpenTelemetry | https://opentelemetry.io/docs/ — concepts and Python instrumentation |
| Observability | Prometheus | https://prometheus.io/docs/ — instrumentation, queries, alerting fundamentals |
| Observability | Grafana | https://grafana.com/docs/grafana/latest/ — data sources and dashboards |
| Observability | Langfuse | https://langfuse.com/docs/ — tracing, evaluation, privacy controls |
| Testing | pytest | https://docs.pytest.org/en/stable/ — fixtures, parametrization, testing basics |
| Testing | Playwright | https://playwright.dev/docs/ — browser testing, assertions, authentication |

Registry manifests declare exact allowed hosts/path prefixes, seed pages, optional sitemap/llms.txt discovery, content type, license/attribution notes, exclusions, publisher/technology relationship, version-address templates/coverage, and per-entry page limits. Verified host/path scope does not itself prove every historical release is supported. Resolve navigation links only within those boundaries; neither a sitemap nor llms.txt grants extra access. Deduplicate LangChain/LangGraph shared-host content by canonical URL within the workspace. For GitHub, fetch explicitly pinned files via the official raw/content endpoint, with that host separately allowlisted.

## Operations, feasibility, and references

Backups include consistent database/storage artifacts, configuration versions, and deletion-journal state, without committed secrets. Test migration failure, restore, stale leases, uncertain provider calls, revoked identities, and overdue cleanup. A restore is complete only after policy/deletion reconciliation and fixed-corpus retrieval/citation checks.

Public-document selection and structural planning are complete; reference hardware, Docker capacity, dependency compatibility, actual OAuth/SMTP setup, model access/prices/output semantics, all 29 source manifests, GitHub App installation/token behavior, and supported parser/version mappings remain implementation verification gates. No code, paid inference, or runtime proof is claimed.

Primary references consulted during planning on 2026-10-28: [LangGraph memory](https://docs.langchain.com/oss/python/langgraph/add-memory), [persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Keycloak administration](https://www.keycloak.org/docs/26.8.1/server_admin/), [Gemini embedding](https://ai.google.dev/gemini-api/docs/embeddings), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Groq models](https://console.groq.com/docs/models), [HF hosted models](https://huggingface.co/inference/models), [HF billing](https://huggingface.co/docs/inference-providers/pricing), [pgvector](https://github.com/pgvector/pgvector), [PostgreSQL full-text](https://www.postgresql.org/docs/current/textsearch-intro.html), [Procrastinate](https://procrastinate.readthedocs.io/en/stable/).

GitHub/dependency primary references for the extension: [GitHub App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app), [user access](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user), [saved-data authorization](https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/best-practices-for-creating-a-github-app#check-authorization-thoroughly-durably-and-often), [Contents API](https://docs.github.com/en/rest/repos/contents#get-repository-content), [pip requirements](https://pip.pypa.io/en/stable/reference/requirements-file-format/), [pyproject](https://packaging.python.org/en/latest/specifications/pyproject-toml/), [npm manifest](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/), [npm lockfile](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/), [PyPI metadata](https://docs.pypi.org/api/json/). Public references do not verify account-specific installation, lock-schema compatibility, or documentation availability.
