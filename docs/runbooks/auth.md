# GitHub authentication

GitHub is the only login provider. Use a GitHub App with Contents read-only, Metadata read-only and selected repositories. Configure `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_SLUG`, `AUTH_ENCRYPTION_KEY` and exact `APP_ORIGIN`; the callback is `/api/v1/auth/callback`. Local HTTP requires the explicit loopback-only exception. Backend secrets never belong in URLs, browser storage or logs.

The implementation uses state, PKCE, single-use flows, encrypted backend token/session storage, serialized refresh and numeric identity rechecks. Browser mutations require Origin/CSRF; GitHub user/App intersection governs repository access. Public profile email is optional and is not verified-email evidence; never link existing users by email. Installation, organization/SSO and revoked user/repository access require real-account verification.

Use [personal-project setup](personal-projects.md) for runtime configuration and [tasks](../tasks.md) for acceptance gaps. There is no OIDC/Keycloak/Google/email runtime, copied authentication test app or retired identity service in active Compose. History is only in [memory](../memory.md).
