# Backend authentication

Implemented 2026-10-30, backend only. The frontend remains a synthetic preview and does not call these routes. Authentication itself creates no memberships. Subsequent [workspace](workspaces.md) and [membership](memberships.md) slices implement explicit owner creation, filtered listing and owner-managed recipient-bound invitations/member changes. Project workflows remain reserved; overall readiness stays 503.

## Configure and start

Use Python 3.12+, uv, Docker Desktop's Linux engine and Compose. Preserve existing `.env` database passwords. For a fresh database, copy `.env.example` only if `.env` is absent and replace placeholders. Generate independent URL-safe random database/admin/client secrets. Generate `AUTH_ENCRYPTION_KEY` with `cryptography.fernet.Fernet.generate_key().decode()` and store it directly in the ignored environment file. Never commit or log secrets.

| Setting | Responsibility |
| --- | --- |
| `APP_ORIGIN` | Browser origin without a path; backend-only local default `http://127.0.0.1:58000` |
| `OIDC_ISSUER` | Exact realm issuer; local `http://127.0.0.1:58080/realms/docweave` |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | Confidential code-flow client; local ID `docweave` |
| `AUTH_ENCRYPTION_KEY` | Fernet key for provider tokens/protocol state and session-bound CSRF derivation |
| `AUTH_LOCALHOST_HTTP` | Explicit loopback HTTP exception; defaults to `false` |
| `OIDC_GOOGLE_ENABLED`, `OIDC_GITHUB_ENABLED` | Enable only after configuring each broker; default `false` |
| `DATABASE_URL` | Restricted application login; never use migration/admin credentials |
| `MIGRATION_DATABASE_URL` | Migration-owner login for explicit migrations only |
| `KC_DB_PASSWORD`, `KC_BOOTSTRAP_ADMIN_PASSWORD` | Separate identity database and bootstrap administrator secrets |

All auth settings absent keeps health/docs available while login returns 503. Partial or unsafe configuration fails startup. Nonloopback HTTP and insecure-cookie settings on nonloopback hosts are rejected. The application origin is normalized to browser casing/default-port rules; discovered issuer must match configuration.

After restoring valid development database credentials:

```powershell
uv sync --project backend --locked
docker compose --profile auth config --quiet
docker compose up -d --wait db
uv run --project backend --locked alembic -c backend/alembic.ini upgrade head
docker compose --profile auth up -d keycloak mailpit
uv run --project backend --locked uvicorn docweave.main:create_app --factory --app-dir backend/src --host 127.0.0.1 --port 58000 --no-access-log --no-proxy-headers
```

Keycloak initialization takes time after its container starts. Check [realm discovery](http://127.0.0.1:58080/realms/docweave/.well-known/openid-configuration), then use the [admin console](http://127.0.0.1:58080/admin/) with `admin` and the bootstrap password. Replace its temporary administrator for long-lived use. [Mailpit](http://127.0.0.1:8025) captures development verification/reset email. SMTP and the identity database publish no host port; exposed services bind only to loopback.

The local realm enables verified email registration/reset, a 12-character password minimum, five-failure brute-force protection, confidential code flow and S256 PKCE. Implicit/password/service-account grants are disabled. The separate identity database uses `identity_pgdata`. Realm import skips existing realms; editing JSON or environment values does not update existing client secrets. Apply later changes deliberately through Keycloak administration. Never delete volumes to fix credentials.

Production requires HTTPS, exact HTTPS callback URIs, delivering SMTP, trusted proxy handling, `AUTH_LOCALHOST_HTTP=false`, and replacement of the local `start-dev`/`sslRequired=none` settings. A future frontend proxy must expose `/api/v1` at `APP_ORIGIN`; this task does not add it.

## Protocol and endpoints

1. Navigate to `GET /api/v1/auth/login?method=email`. `google`/`github` are allowlisted alternatives when enabled. State, nonce and S256 PKCE are generated server-side. The verifier/nonce stay encrypted in a ten-minute database transaction bound to the opaque HttpOnly `docweave_login` cookie.
2. Keycloak handles credentials, registration, verification, account activation and reset. `/api/v1/auth/callback` atomically consumes the browser-bound transaction, exchanges the code with PKCE, and validates RS256 signature, issuer, audience, authorized party, nonce, expiry and strictly verified email. Only issuer/subject provisions an identity; same-email subjects remain separate. It rotates the application session and redirects to fixed `APP_ORIGIN/`. No backend landing page is implemented at `/`; backend clients can inspect the callback without following its final redirect, then call `/me`.
3. `GET /api/v1/me` returns `id`, `display_name`, `verified_email` and session-bound `csrf_token`, including before workspace membership exists. The opaque `docweave_session` cookie is HttpOnly, SameSite=Lax and Secure except explicit loopback development. Only its hash is stored; provider tokens are encrypted server-side. Responses carry `Cache-Control: no-store`, a request ID and `Referrer-Policy: no-referrer`.
4. `POST /api/v1/auth/logout` requires the session, exact `Origin: APP_ORIGIN` and `X-CSRF-Token` from `/me`. It deletes the session and expires its cookie; replay fails. Private reserved routes enforce those same dependencies before returning 501. Public catalog/provider stubs remain 501 without login. Runtime OpenAPI declares cookie and CSRF together for mutations.

Sessions expire at the earliest of ID-token expiry, access-token expiry and eight hours; the local realm's access-token lifetime is fifteen minutes. No automatic refresh or global Keycloak/social-provider logout is implemented. An IdP revocation alone does not instantly revoke an existing app session; bounded expiry still applies. Application logout revokes immediately.

PostgreSQL limits admission to ten logins/minute per socket-peer hash across API processes, with `Retry-After: 60`; Keycloak separately protects passwords. Trust forwarded headers only through an explicit proxy policy. Expired transactions/sessions/rate buckets are removed on subsequent login attempts.

Invalid protocol transactions return safe 400, missing/expired sessions 401, bad origin/CSRF 403, invalid methods 422, throttling 429 and unavailable identity configuration/services 503. Do not reflect/log provider errors, credentials, callback queries, cookies or tokens. Keep access logging off unless redaction exists. CSRF tokens belong in transient client memory and headers.

## Social broker configuration

Create operator-owned Google/GitHub OAuth clients and configure Keycloak aliases exactly `google`/`github`, with callbacks:

- `http://127.0.0.1:58080/realms/docweave/broker/google/endpoint`
- `http://127.0.0.1:58080/realms/docweave/broker/github/endpoint`

Store broker secrets only in Keycloak. Retain its default secure first-broker/account-linking flow; do not add automatic email linking or blindly trust external email. Ensure the resulting Keycloak identity has a verified email, then enable the matching backend flag and restart the API. GitHub login does not grant repository access. Actual social login requires account-specific verification; synthetic routing tests do not establish it.

References: [Keycloak OIDC endpoints](https://www.keycloak.org/securing-apps/oidc-layers), [Keycloak administration](https://www.keycloak.org/docs/26.8.1/server_admin/), [Authlib Starlette OIDC integration](https://github.com/authlib/authlib/blob/main/docs/oauth2/client/web/starlette.rst).

## Verification and recovery

```powershell
docker compose --profile test up -d --wait test-db
uv run --project backend --locked pytest backend/tests -q -W error
# Explicit smoke requires the local auth profile; it is not collected by default:
uv run --project backend --locked pytest backend/tests/smoke_auth.py -q -W error
docker compose --profile test stop test-db
```

The ordinary suite uses real restricted-role PostgreSQL and signed synthetic OIDC tokens with fake provider transport. The explicit smoke uses the guarded disposable app database, live local Keycloak and captured SMTP: registration/verification/activation, password reset, sessions, logout and replay rejection. It creates synthetic `@example.test` identities, never sends real inbox email and never touches the development app database. Its HTTP client emulates Chrome's Secure-cookie exception on loopback; isolated Chrome verified that behavior. This is backend protocol evidence; frontend integration is deferred. The form parser has a small self-check.

Migrations run explicitly through Alembic. `0002_auth` grants runtime CRUD only on auth tables plus a fixed-search-path identity upsert function; domain tables retain general write restrictions and tenant RLS. Only the actor's own user record is readable before membership. Workspace/project rows still require membership. Validate downgrade/re-upgrade and `alembic check` only on the guarded disposable target, with migration credentials loaded through your local secret mechanism; never paste secrets into tracked scripts/history.

Stop identity services with `docker compose --profile auth stop keycloak keycloak-db mailpit`; the identity database persists. The reset retained `docweave_pgdata` and older `docweave_keycloak_pgdata` but removed their containers/plaintext credentials. Neither old volume was altered. The new ignored `.env` is valid for disposable tests and the new identity profile; restore the original development credentials before starting `db`, migrating development or using `DATABASE_URL`. Environment changes alone do not rotate existing PostgreSQL role passwords.
