# Synthetic FastAPI to PostgreSQL runbook

This is a synthetic fixture, not official product documentation.

## Connection

Keep the PostgreSQL connection URL on the backend. Create an engine once and a database session per request. Do not put credentials in browser bundles or logs.

## Access

Set workspace and actor context inside each transaction. Check current membership and collection grants. Do not run the API with the migration-owner login.

## Troubleshooting

If a connection is refused, check the host, port and running database service. If authentication is rejected, check the role and matching pg_hba.conf rule; do not weaken authentication to trust.
