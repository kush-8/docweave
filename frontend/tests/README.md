# Frontend tests

- `e2e/`: GitHub login, project setup, draft protection, processing permissions, durable chat states, evidence, responsive layout and accessibility.
- `architecture/`: layer boundaries and pure URL handling.
- `support/api.ts`: deterministic API fixtures. These tests do not establish live backend/provider compatibility.

Run `npm test` from `frontend/`. Playwright starts Vite. For installed Chrome, set `$env:PLAYWRIGHT_CHANNEL='chrome'` first. Run `npm run build` and `npm run lint` for type/build/static checks. Generated traces and browser results stay ignored under `test-results/`.
