# Backend invitations and member management

Authorized by the user's backend-only continuation after the workspace slice. Implements the existing member-list/change/remove and invitation-create/list/revoke/accept contracts in `backend/openapi.yaml` and the identity/tenancy rules in `docs/architecture.md`. Frontend, project CRUD, collection grants, budget/inference and the rest of Task 1 remain deferred.

Using Superpowers TDD/inline execution and independent review, with Ponytail scope limits. Reuse the current auth, tenant transaction helper, owner guards and narrow SECURITY DEFINER pattern. Preserve all pending prior backend and unrelated frontend/doc work. Test only the guarded disposable database; original development credentials remain unavailable.

## Implementation choices

- `0004_memberships.py` + `models.py`: invitation record with workspace, issuing user, normalized recipient email, role, unique token hash, expiry/consumed/revoked timestamps. Runtime gets no direct domain writes; fixed-search-path functions enforce current owner authority. Serialize all membership/invitation mutations on the workspace row, rechecking owner status after acquiring its lock. Last-owner removal/demotion returns 409/last_owner even under concurrent requests. Losing owner status revokes that issuer's pending invitations.
- `memberships.py`: owner-only member and invitation lists, PATCH/DELETE membership, POST/DELETE invitation, and authenticated CSRF-protected token acceptance. Recipient identity comes from the current verified DB user; token/expiry/state/recipient failures share safe 404. Tokens have 256 random bits, are hashed at rest, expire after 48 hours, and are revealed only in the creation link. Existing members get 409/already_member without role elevation or token consumption. No real invitation email is sent.
- `pagination.py`: extract the existing encrypted actor/resource-bound cursor/page code and reuse it for workspace, member and invitation lists (25 default/100 max; stable creation-time/UUID order). Bind new lists to their workspace/category. Preserve current workspace cursor format.
- Current owner reads/writes are rechecked inside narrow DB functions; HTTP guards alone cannot authorize a delayed mutation. Known SQLSTATE outcomes map to existing safe API errors. Raw DB/provider details and invitation tokens are not reflected/logged.
- Use Pydantic email validation with its maintained validator dependency, without DNS/delivery checks. Reject unknown fields and invalid role/email input. Match verified recipient email case-insensitively; identity remains issuer/subject, with no account merging.
- Update `main.py`, existing caller/test expectations, runtime/draft docs, cleanup fixtures and runbooks with implemented behavior. Keep cookie AND CSRF requirements.

## Execution/evidence

- [x] Run baseline; write failing tests for invite lifecycle, recipient/session/CSRF/owner boundaries and last-owner races.
- [x] Implement minimal migration/functions, shared pagination and handlers; verify lifecycle, atomicity and access changes.
- [x] Verify pagination/secret omission, function grants, schema/downgrade safety, stale-owner recheck, concurrent acceptance and owner changes.
- [x] Run complete backend suite, config/lock/docs checks; independently review, reproduce/fix material findings and record final evidence.

Failure walkthrough: two owners concurrently demote themselves. Both may pass the HTTP owner dependency, but their database mutations take the same workspace lock and recheck current roles/owner count. The first succeeds; the second sees one remaining owner and returns 409. Invitation acceptance uses the same lock and atomically adds membership plus consumes the token, so a second accept cannot grant anything.

## Final evidence — 2026-10-30

- Baseline full backend suite -> **253 passed** with warnings as errors.
- RED: first invitation lifecycle test observed reserved HTTP 501 instead of expected 201 before implementation.
- Initial lifecycle/security/race tests -> **19 passed**. Input fixtures were corrected to reserved `example.com` addresses after confirming email-validator deliberately rejects special-use `.test`; no production validation was weakened and no email is sent.
- Held-lock tests use the runtime role's own activity visibility, not extra monitoring privileges. They confirm expiry is rechecked after waiting and a queued creator that loses ownership returns 403 without insertion. Stale direct-function calls also fail closed.
- Final membership suite -> **29 passed**. Includes two-client owner self-removal/demotion races, concurrent acceptance once, issuer ownership-loss revocation, already-member non-escalation, verified recipient/CSRF/input checks, cursor scope/secret omission and private function/table permissions.
- Final complete command: `uv run --project backend --locked --cache-dir backend/.uv-cache pytest backend/tests -q -W error --tb=short` -> **282 passed**. Full suite exercises model alignment and disposable upgrade/downgrade/re-upgrade through `0004_memberships`.
- Independent read-only review found no material defect in locking, authority/token checks, grants, pagination or contracts. Its remaining queued-owner coverage gap was filled and verified before the final full run.
- Locked/offline uv sync, Compose validation, whitespace and updated local documentation links passed.
- No frontend, real invitation email, paid APIs, production/persistent DB changes, merge, push or deployment. Existing pending work is preserved on `codex/auth`; original development credentials still require recovery.
