# Cloudflare Free Staging Runtime

## Safety boundary

- The staging Worker serves the existing static Coach UI and the existing FastAPI Core.
- Staging uses in-memory persistence by design. It is not a source of truth and must not receive real athlete records.
- OIDC remains enabled. The API does not trust client-supplied actor, role, or tenant headers.
- The staging configuration has no Hyperdrive binding and contains no database credentials.
- Deployment is manual only; pushes and pull requests do not publish a Worker.

## Deploy staging

1. Add GitHub repository Actions secrets named `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
2. The API token should be scoped to the account and have permission to edit Workers scripts.
3. Open Actions → **Cloudflare Free Staging Deploy** → Run workflow.

The workflow deploys only the isolated `kaizo-coach-core-staging` Worker. It does not connect to Neon or alter production data.

## Production database is deliberately not wired yet

Before connecting any production database:

1. Rotate the Neon database password that was previously stored in the retired Railway environment.
2. Create a separate Neon branch for staging verification; do not test against the live athlete database.
3. Create a Cloudflare Hyperdrive configuration for that branch with query caching disabled. Stale cached ownership or authorization reads are not acceptable.
4. Add the resulting Hyperdrive ID as the `HYPERDRIVE` binding in `wrangler.jsonc`.
5. Verify persistence, Coach-to-Coach isolation, tenant isolation, audit durability, and read-after-write behavior before considering production.

The Worker uses the Hyperdrive connection string at runtime. It must never be copied into source control or chat. Synchronous PostgreSQL operations are serialized in the Worker entrypoint as required by Cloudflare's Python Workers guidance.

## Free-plan constraints

Cloudflare Workers Free currently allows 100,000 requests/day and 10 ms CPU time per HTTP request. Hyperdrive Free allows 100,000 SQL statements/day. Python Workers support for Hyperdrive is documented, but the Python Hyperdrive integration is still a newer runtime path. These limits must be measured with the real Coach flows; this staging setup is not a claim of production readiness.
