# Backend invitations and member management

Implemented 2026-10-30, backend only, on top of [auth](auth.md), [workspaces](workspaces.md) and migration `0004_memberships`. No invitation email is sent. Project workflows, frontend integration, collection grants, jobs/inference and full Task 1 remain incomplete.

## Operations

All mutations require the application session, exact configured Origin and `X-CSRF-Token` from `/me`. Owner operations require current workspace ownership. Nonmembers receive safe 404; visible insufficient roles receive 403/`forbidden`. Owner authority is checked again inside the database transaction after taking the workspace lock.

| Operation | Result |
| --- | --- |
| `GET /api/v1/workspaces/{workspace_id}/members` | Owner-only paginated members, including IDs, role and display name |
| `PATCH /api/v1/workspaces/{workspace_id}/members/{user_id}` | Owner changes a current member's role; HTTP 200 membership |
| `DELETE /api/v1/workspaces/{workspace_id}/members/{user_id}` | Owner removes a current membership; HTTP 204 |
| `POST /api/v1/workspaces/{workspace_id}/invitations` | Owner issues a 48-hour invitation; HTTP 201 metadata and secret-bearing acceptance URL |
| `GET /api/v1/workspaces/{workspace_id}/invitations` | Owner-only paginated metadata; no tokens, hashes or acceptance URLs |
| `DELETE /api/v1/workspaces/{workspace_id}/invitations/{invitation_id}` | Owner revokes an unconsumed invitation; HTTP 204, repeat revocation is harmless |
| `POST /api/v1/invitations/{token}/accept` | Intended currently verified recipient joins atomically; HTTP 200 membership |

Member PATCH accepts only a required `role`, one of `owner`, `maintainer`, `member`. Invitations require exactly `email` and `role`:

```json
{"email":"colleague@example.com","role":"member"}
```

Unknown fields, invalid roles and invalid email addresses return safe 422. Email validation uses Pydantic/email-validator without DNS or delivery checks; it does not prove mailbox ownership. Display-name address syntax is rejected. Reserved `.test` domains are rejected by that validator; synthetic invitation tests use `example.com` and never send email. Keycloak's verified current identity is the acceptance authority. Matching is case-insensitive; no email-domain inference, plus-tag stripping, account linking or issuer/subject merging occurs.

Both lists use default 25/max 100 items and opaque encrypted cursors. Member order is `(membership.created_at,user_id)`; invitations use `(created_at,id)`. Cursors bind to the actor, workspace and list category, and cannot be reused across workspaces/categories/users. Ownership is rechecked for every page. Responses omit internal ordering fields and secrets. Existing workspace cursors retain their previous format.

## Invitation lifecycle and secret handling

The API generates 32 random bytes (256 bits), stores only the SHA-256 token hash, and returns the raw URL-safe token only in the creation response's `acceptance_url`. That URL references the POST acceptance endpoint; it is not a GET action or implemented frontend invitation page. A future frontend can present confirmation and submit the protected POST. Do not put the link in analytics, logs or unprotected browser storage. Keep access logging disabled or redact this path segment. Responses carry no-store, request IDs and no-referrer policy.

Invitation status is computed as `pending`, `accepted`, `revoked` or `expired`. Acceptance checks current verified DB email, token/hash, state, expiry and the issuing user's current owner membership after waiting for the workspace lock. Unknown, malformed, expired, revoked, consumed and wrong-recipient tokens all return the same safe 404. Unauthenticated/unverified sessions fail before acceptance. A failed recipient check does not consume the invitation.

The membership insert and consumption timestamp commit together. Concurrent acceptance grants exactly once; replay returns 404. A recipient who already belongs to the workspace receives 409/`already_member`, preserving their current role and leaving the invitation unconsumed. Change their role through the explicit owner PATCH endpoint. Acceptance never trusts client-provided identity, email, role or workspace claims.

When an issuing owner is removed or demoted, their still-pending invitations are revoked in that transaction. An invitation cannot restore a former owner's authority. Existing accepted memberships remain until explicitly changed/removed; expiry/revocation does not undo a previously accepted membership. Owner revocation of an already-consumed invitation returns 404.

## Last-owner and transaction safety

Removing/demoting the last actual owner returns 409/`last_owner`; an unchanged owner role is allowed. Pending invitations promising ownership do not count as owners. Every authorized membership/invitation writer takes the same workspace row lock and rechecks current authority. Thus two owners concurrently leaving/demoting cannot both succeed and leave the workspace ownerless. Reads also use the owner-lock helper for a consistent authorized result.

Expiry uses `clock_timestamp()` after acquiring locks, not the transaction-start timestamp. A request that began before expiry but waited past the deadline is rejected. A caller that passed the HTTP owner dependency but lost ownership while waiting is also rejected before writing.

Failure walkthrough: Alice and Bob are both owners and concurrently PATCH themselves to member. Alice's transaction locks the workspace, confirms two owners and demotes her. Bob's transaction then obtains the lock, confirms his still-current ownership, sees he is the only owner, and returns 409. The database retains one owner. The test suite also queues an invitation creation behind a held lock, demotes its caller while it waits, and verifies 403 without an invitation insert.

## Storage and verification

The invitation table is private, RLS-enabled and has no runtime table SELECT/DML grants. Runtime may execute only the narrowly scoped public-facing functions. The locking helper has no runtime or PUBLIC EXECUTE privilege; all functions have fixed search paths, and PUBLIC execution is revoked. General workspace/membership writes remain denied. Lists/acceptance never return token hashes. Invite records include issuer, recipient, role, expiry and terminal timestamps; a constraint prevents simultaneous consumed/revoked states.

Restore original development credentials before applying migrations to the preserved development volume. This task verified only the guarded disposable PostgreSQL target, without changing existing persistent data:

```powershell
docker compose --profile test up -d --wait test-db
uv run --project backend --locked pytest backend/tests/test_memberships.py -q -W error
uv run --project backend --locked pytest backend/tests -q -W error
docker compose --profile test stop test-db
```

The suite uses real signed test OIDC identities and restricted PostgreSQL sessions, with two authenticated clients for races. It verifies lifecycle, secret omission, current recipient/owner checks, input/CSRF, last-owner/concurrent acceptance, held-lock expiry and stale-owner rejection, cursor boundaries, direct storage/helper permission denial, schema/grants, and disposable downgrade/re-upgrade. Lock observation uses the runtime's own activity visibility; no monitoring/admin privilege was granted. No live identity-provider, delivery SMTP or frontend test is needed for this slice; those implementations are unchanged/deferred.
