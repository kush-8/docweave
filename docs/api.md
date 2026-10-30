# DocWeave API guide

Status: backend authentication, workspaces, member management, invitations and manual project context implemented 2026-10-30; other domain contracts remain draft. Manual projects have atomic owner-only default collections and durable pending documentation requests, without approved-source jobs or external processing. Project child stubs now also check current project membership before 501. Readiness stays 503; frontend integration, GitHub reviewed-stack creation, collection grants, import workers and AI remain unimplemented.

[openapi.yaml](../backend/openapi.yaml) is the machine-readable contract, using [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html). Open the file in an OpenAPI 3.1-compatible local viewer to browse operations and schemas. No hosted editor, generated SDK, API server or Swagger UI installation is required by this documentation change. Avoid uploading private specifications or credentials to third-party viewers.

[architecture.md](architecture.md#public-contracts) remains authoritative for behavior and security. This draft makes its route families concrete; field names and the additional lifecycle routes below are proposed implementation defaults. Reconcile changes with this file, the YAML, and affected planning documents before implementing them. The draft version is not a released compatibility promise.

Use the [README run instructions](../README.md#run-the-api-skeleton) and [auth runbook](runbooks/auth.md). `/docs` and `/openapi.json` describe runtime responses and cookie/CSRF security. The YAML also contains future domain contracts; registered routes do not imply domain implementation.

## Base URL and conventions

The same-origin base path is `/api/v1`. No hostname, frontend port or production deployment is assumed. Health endpoints also use this prefix. JSON uses `snake_case`, opaque UUID resource IDs, UTC RFC 3339 timestamps, and decimal **strings** for USD. GitHub repository IDs are positive integers. Treat IDs as opaque and authorize their resources server-side.

Lists return `{ "items": [...], "next_cursor": null }`. Omit `cursor` for the first page; pass the returned cursor unchanged for the next page. `limit` defaults to 25 and accepts 1–100. A null cursor ends pagination. Cursors bind to the actor, resource, filters and ordering; authorization is reapplied on every page. Lists use a stable server order; transcripts use ascending turn sequence. Embedded grant/review/fact sets are bounded resource representations rather than independently paginated lists.

Implemented workspace/project listing uses ascending `(created_at,id)` keyset order and encrypted actor/resource-bound cursors, reapplying current membership on every page. POST `/workspaces` accepts only a nonblank, NUL-free name (trimmed) and creates the signed-in actor's owner membership atomically, without setting a spending allowance. Member/invitation operations and project creation/editing require current ownership; workspace/project context reads require membership. Outsiders receive 404; visible insufficient roles receive 403/`forbidden`. See [workspace details/evidence](runbooks/workspaces.md).

Every response carries `X-Request-ID`; errors and durable acceptance bodies also carry `request_id`. Private responses use `Cache-Control: no-store`. Never cache private content, tokens or drafts in persistent browser storage. JSON request schemas reject unknown fields; optional fields are omitted unless their schema explicitly permits null. Clients should tolerate additional response fields.

## Login, sessions and authorization

Navigate to `GET /auth/login?method=email|google|github`. Keycloak owns email registration, verification, password reset and account-linking flows. `/auth/callback` validates state, nonce, issuer, audience and PKCE before establishing the opaque `docweave_session` cookie. Provider tokens remain server-side. Cookie defaults are HttpOnly, SameSite=Lax, Path=/ and Secure, with an explicit localhost-only development exception for Secure.

After login, `GET /me` returns the actor and a session-bound `csrf_token`. Every POST, PUT, PATCH and DELETE requires both the session cookie and `X-CSRF-Token`, with origin validation. OAuth callbacks use single-use protocol state. `POST /auth/logout` invalidates the application session and expires its cookie. Do not put credentials or CSRF tokens in URLs, logs or localStorage. Invitation token path segments and OAuth callback query values must be redacted from access logs/traces; invitation pages use a no-referrer policy.

Implemented auth: browser-bound login transactions expire in ten minutes; sessions expire no later than ID/access-token expiry or eight hours. Tokens are encrypted server-side and cookie identifiers are hashed. No automatic refresh/global IdP logout is performed. Social methods require configured brokers and backend flags. `/me` works without membership; login never creates one. Workspace membership and manual project-context policies are implemented; broader collection/conversation policies remain planned.

Member roles are changed only through owner PATCH, and removal/demotion of the last owner returns 409/`last_owner` even under concurrent requests. Invitation links are returned only once, reference a protected POST, expire after 48 hours and store only token hashes. Acceptance atomically verifies current recipient/issuer authority and state after lock waits, adds membership and consumes the token. Invalid/wrong-recipient/replayed tokens return safe 404; existing members return 409/`already_member` without changing role or consuming it. An issuer losing ownership revokes their pending invitations. Owner lists are paginated and never contain tokens/hashes/links. No invitation email or frontend page is implemented. See the [membership runbook](runbooks/memberships.md).

Workspace owners manage memberships, invitations, projects, grants and processing approvals. Maintainers write only to explicitly writable collections. Members read explicitly readable collections and use their own conversations. Write grants do not elevate a member's role. Owners retain collection management authority; new collections start owner-only. Invitation acceptance requires the intended verified recipient, consumes the token atomically, and defaults to a 48-hour expiry. Removing or demoting the last owner is a conflict.

Conversations, titles and turns belong to their author, including within a shared workspace. An owner cannot read another author's conversation. Private GitHub-derived context additionally requires the viewer's own current upstream access; an installation token or workspace membership is insufficient. Inaccessible resources return safe 404 errors. An upstream verification outage fails closed without returning retained private labels.

Project and collection processing policies are separate. Project policy covers private project context/messages/history; collection policy covers its private knowledge. Approve every actual processor/backend that receives private data, including Gemini retrieval with Groq/Hugging Face answers. Profile metadata from `/providers` lists processor IDs; approving an HF brand alone does not approve an unspecified backend. Empty replacement approval lists revoke all processors.

Manual project POST accepts name, goal, exactly one nonempty manual stack or reviewed-stack ID, plus optional context strings. The reviewed-ID branch currently returns 501 without writes. Manual dependency IDs are server-generated; declared/resolved versions remain null, and omitted docs targets stay unresolved. No catalog/version selection is approved yet: all dependency IDs are returned in `pending_dependency_ids`, `job_ids=[]` and `source_state=pending_review`. Context, owner-only default collection and local pending requests commit together. Project PATCH requires a positive integer `expected_revision` plus at least one editable field; stale edits return 409/`revision_conflict`. Omission preserves context; empty strings clear optional fields. Explicit null, NUL characters and unknown fields are rejected. Replacing a stack supersedes old pending requests and gives replacement entries new IDs. See the [project runbook](runbooks/projects.md).

## Operation map

The YAML contains every method, request, response and schema. These are the main workflows:

| Workflow | Operations |
| --- | --- |
| Health and identity | Liveness/readiness; login/callback/logout; current user |
| Tenants | List/create workspaces; owner list/change/remove members; issue/list/revoke/accept invitations |
| Project setup | List/create/read/edit projects; project processing policy; public catalog/provider profiles |
| Knowledge | List/create collections; replace grants/processor approvals; import/list/refresh/delete sources; upload/read/replace/delete/reindex documents; list versions |
| GitHub | Separate connect/callback/status/disconnect; accessible repositories/branches; initial scan/read/delete/review; project rescan/apply |
| Documentation | Submit discovery or an official-source proposal; read immutable candidates; approve exact scopes and explicit version fallbacks |
| Activity | List authorized project jobs; read status; explicitly retry eligible work |
| Conversations | Create/list/read/delete own conversation; append/list turns; recover status; explicit retry; inspect captured citation spans |
| Usage | Project/workspace-only monthly usage and allowance; no cap-changing or global financial endpoint |

## Manual project to cited reply

1. Sign in, then list or create a workspace. An owner creates a project with `name`, `goal`, and a nonempty `stack`. A GitHub setup instead supplies a confirmed `stack_review_id`; exactly one stack input is allowed. Optional context is `architecture_notes`, `environment`, and `constraints`.
2. Project creation returns the project, its owner-only `default_collection_id`, `job_ids`, and `pending_dependency_ids`. Approved catalog/version imports are committed with project creation. Unknown origins, unresolved versions and unaccepted fallbacks remain pending. Missing allowance or provider capacity produces visible waiting state.
3. The owner reviews and replaces project/collection processor approvals. Each replacement includes `expected_revision`; stale revisions return 409. The same revision guard protects project edits and collection grants. Optional text can be cleared with an empty string; omitted fields stay unchanged.
4. Upload one file per multipart request to `/collections/{collection_id}/documents`. The only field is `file`; let the browser generate the multipart boundary. PDF/TXT/Markdown/DOCX support is planned, with 20 MiB/file, 500 PDF pages, two million extracted characters, and bounded parser resources. Image-only/encrypted PDFs are unsupported; OCR is excluded. Missing processor approval holds work in `awaiting_approval`. Malware scanning status remains explicit, including disabled/unavailable.
5. Poll returned jobs. A replacement or refresh stages a version before atomic activation; failure keeps the last good version. Select authorized ready collections and an enabled answer profile to create a conversation. The profile stays fixed. Omitted `collection_ids` captures the current eligible readable set; `[]` explicitly selects none. Future collections are never silently added.
6. Append a message, retain its accepted `turn_id`, and poll its `status_url`. Read citations from their returned `evidence_url`; they reference captured immutable spans, not a live fetch of the original URL.

Illustrative browser request after the application exists; the conversation ID comes from creation and the session cookie is sent by the browser:

```javascript
const meResponse = await fetch('/api/v1/me', { credentials: 'same-origin' });
if (!meResponse.ok) throw new Error('Sign in before sending a message.');
const me = await meResponse.json();
const conversationId = '3c082493-e1ac-4a86-a11a-262568c4e521';
const submission = {
  message: 'How should this service protect its documentation uploads?',
  idempotency_key: crypto.randomUUID(), // Retain this body for transport retries.
};
const response = await fetch(`/api/v1/conversations/${conversationId}/turns`, {
  method: 'POST',
  credentials: 'same-origin',
  headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': me.csrf_token },
  body: JSON.stringify(submission),
});
if (response.status !== 202) throw await response.json();
const accepted = await response.json(); // Save turn_id; poll status_url.
```

## Turn acceptance, recovery and retry

`POST /conversations/{conversation_id}/turns` accepts only `message` and `idempotency_key`. The server supplies current project context, source scope and committed history. It never accepts a client transcript, author, tenant claim or per-turn profile override.

| Situation | Contract |
| --- | --- |
| New valid submission | 202 after durable turn/job commit; returns `turn_id`, `status_url`, `request_id` |
| Same conversation, key and body | Same turn reference with 202, including during execution or after completion |
| Same key, different body | 409 `idempotency_conflict` |
| Different key while a turn is active | 409 `turn_in_progress` |
| Lost acceptance response | Resubmit the identical retained body/key; never generate a new key to recover acceptance |
| Reload after acceptance | GET the accepted turn; do not POST it again |
| Worker cannot establish whether a provider completed | `completion_unknown`; no automatic paid replay |
| User explicitly retries uncertain completion | POST `/turns/{turn_id}/retry` with a new retry key and `acknowledge_possible_charge: true`; new reservation/turn, same fixed profile |
| Remembered source revoked/deleted | `blocked_policy`; hide affected content, pause work and offer a fresh conversation without copied memory |

Retain original send keys for the retained conversation lifecycle; retry keys bind to the original resource and retry intent. Claim keys atomically with a request hash and unique constraint. Idempotency prevents duplicate application dispatch; it cannot guarantee exactly-once provider billing.

Turn execution states are `queued`, `running`, `completed`, `failed`, `completion_unknown`, and `blocked_policy`. Only `completed` exposes a validated `result` with kind `answered`, `needs_clarification`, or `abstained`. Clarification is an ordinary persisted reply; the user's answer is the next message. `failed` is operational failure, distinct from evidence-based abstention. A safe error explains retry eligibility; `retryable: true` never authorizes an automatic paid replay.

Poll while visible, back off while hidden, respect an optional `Retry-After`, and stop polling terminal states. A status read is always safe to repeat. `blocked_policy` views omit message/result and affected titles; transcript reads return a safe 409 rather than revoked text. Summarization changes model context, not stored transcript length. Context/source revisions, profile/backend, usage and duration accompany completed results. No token stream, turn cancellation or raw checkpoint endpoint is promised.

Other mutations have no blanket retry guarantee. After uncertain transport acceptance, recover resource/job state before repeating them. Job retries use the explicit keyed retry operation and recheck current authority and budget.

## GitHub scan and documentation review

GitHub repository connection is separate from GitHub sign-in. `POST /connections/github/connect` returns an authorization URL with state bound to the current user. The callback revalidates that identity and the user/App intersection. Repository and branch lists expose only currently eligible choices. Contents read permission covers repository contents broadly; the application's fetch allowlist restricts actual reads to supported metadata.

An initial scan takes `workspace_id`, `repository_id`, optional `branch` (default branch if omitted), and `application_path` (empty for root). It pins one commit. Scans are bounded to 20,000 tree entries, depth eight, 100 metadata files, two MiB/file, ten MiB aggregate and 200 GitHub requests. Caps, unsupported formats and ambiguity stay visible as partial/incomplete facts. Raw configs, credentials and private URLs are not persisted or sent to models/discovery.

The scan separates declarations, lockfile resolutions/conditions, dependency role/directness and redacted provenance. A review selects fact IDs and explicit documentation targets, with optional role/directness corrections, without overwriting detected facts. Unknown roles require a user choice; constraint-only entries never become documentation dependencies. A goal is still required when creating the project.

After project creation, discovery works on project-owned dependency IDs, at most 20 per batch. `identifier_lookup_consent_ids` explicitly approves identifier-only public lookup for an exact subset of that batch; omission consents to none. A server-stored revision binds the consent to that work and is rechecked before dispatch. Optional `proposed_sources` lets an owner propose a public official-document URL and docs target for a dependency when discovery cannot find one; it creates an immutable review candidate and never authorizes content fetching by itself.

Read stored candidates from GET `/projects/{project_id}/documentation/discover`. Approve immutable `candidate_ids`, an explicit subset of `accepted_fallback_ids`, and the target `collection_id`. The server validates scope/version/current policy and commits approved selections/import jobs. Approval is project-scoped; it cannot promote global catalog trust, override public-address/redirect/robots restrictions, guess latest, or claim exact coverage from a publisher's major/minor documentation. Unavailable documentation stays unavailable.

A manual rescan produces a new candidate diff; review it before `/repository/apply` with `review_id` and `expected_revision`. Branch movement alone never edits context. Disconnect deletes the user's local credentials immediately and pauses affected private context. Explicit scan deletion removes retained analysis under the deletion policy; independently eligible colleagues keep their own connection.

## Errors, usage and deletion

Errors use a stable `code`, safe `message`, `request_id`, and `retryable`. Optional validation `fields` contain locations/codes only. Do not depend on human message text.

| HTTP | Example codes | Client behavior |
| --- | --- | --- |
| 400 | `invalid_request`, `invalid_cursor`, `invalid_oauth_state` | Correct the request; do not retry blindly |
| 401 | `authentication_required` | Sign in and recover accepted work |
| 403 | `csrf_invalid`, `forbidden`, `processing_approval_required` | Refresh session token or obtain visible-resource authority |
| 404 | `not_found` | Generic missing/hidden resource, including invalid invitations |
| 409 | `idempotency_conflict`, `turn_in_progress`, `revision_conflict`, `last_owner`, `conversation_blocked`, `retry_not_allowed`, `charge_acknowledgement_required` | Resolve the named state; do not replace an original key to bypass a conflict |
| 413 / 415 / 422 | `file_too_large`, `unsupported_media_type`, `validation_error` | Correct input; failures may also appear asynchronously in a job |
| 429 | `rate_limited`, `workspace_budget_exceeded` | Respect server retry information when present |
| 503 | `upstream_verification_unavailable`, `application_capacity_unavailable` | Fail closed; retry safe reads later without disclosing global spend |
| 500 | `internal_error` | Preserve request ID; recover mutation acceptance before repeating |

Usage queries accept optional `month=YYYY-MM` with Asia/Calcutta calendar boundaries. Reports contain only the requested project/workspace aggregates and that workspace's operator-assigned allowance. Decimal USD strings distinguish metered, outstanding reserved, and retained uncertain amounts; these buckets must not be double-counted. A null allowance means none has been assigned. Global balances and cap mutation remain operator-only. Missing bounded pricing disables a profile.

Deletion returns 202 only after access is removed and the cleanup journal is durable. Local bytes, chunks, affected messages/summaries/checkpoints/writes are cleaned within 24 hours while services run; backups expire within seven days. Overdue cleanup runs before traffic resumes after downtime. Content-free audit retention is 90 days. Ordinary refresh/replacement retains authorized cited versions; conversations and referenced snapshots otherwise remain until explicit deletion. Local deletion cannot recall already-dispatched provider data or charges.

## Draft decisions and verification boundary

The architecture already defines the route families, tenant/processor policy, cursor limits, durable-turn states, provider immutability, version review and retention. This draft chooses concrete cookie/header names, snake_case envelopes, UUID wire IDs, body-based idempotency keys, revision guards, owner-only default collection creation and explicit retry request shapes. Lifecycle details made concrete here include member/invitation item routes, source deletion, document read/replacement, project processing policy, project activity listing, stored discovery reads/proposals, scan deletion and turn retry. They support existing accepted flows and remain draft implementation decisions.

YAML parsing, duplicate keys, local references, operation/path parameters, security declarations, schema syntax and representative valid/invalid payloads can be checked before runtime exists. OpenAPI structural validation uses the [official OpenAPI 3.1 schema](https://spec.openapis.org/oas/3.1/schema/2022-10-07). Schema validation alone does not prove application authorization, safe fetching, budget reservations, idempotent dispatch or provider behavior. During implementation, compare FastAPI's generated specification with this contract and add behavioral tests under the owning tasks in [tasks.md](tasks.md); no implementation milestone is completed by this documentation.
