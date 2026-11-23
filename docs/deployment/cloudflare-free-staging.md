# Cloudflare Free Staging Runtime

## Safety boundary

- The repository-root `wrangler.jsonc` is a Staging-only configuration. Its Worker name is `kaizo-coach-core-staging`.
- Staging uses in-memory persistence by design. It is not a source of truth and must not receive real athlete records.
- OIDC remains enabled. The API does not trust client-supplied actor, role, or tenant headers.
- The Staging configuration has no Hyperdrive binding and contains no database credentials.
- The GitHub Actions deployment is manual only and is guarded so its credential-bearing job runs only from `main`.
- The deploy command passes `--config wrangler.jsonc` explicitly and validates the Worker name, memory-only mode, and absence of Hyperdrive before deployment.

## Critical boundary for the existing Production Worker

The existing Cloudflare Git-connected Worker named `kaizo-system` is a separate Production target. It must not consume the repository-root Staging configuration:

- Do not rename the root Staging Worker to `kaizo-system`.
- Do not use `pywrangler deploy` from the Production Worker build integration while it resolves to the root Staging configuration.
- Disconnect the repository Git integration from the Production Worker, or configure a separately reviewed Production project/root with its own Worker configuration and production-specific bindings.
- Connect this repository-root configuration only to the dedicated `kaizo-coach-core-staging` Worker if Cloudflare Git-connected builds are required.
- A failed `Workers Builds: kaizo-system` check is not evidence of a failed Staging deployment and must not be retried as a way to deploy Staging.

Cloudflare dashboard build settings cannot be changed through the repository. The Production Git integration must be corrected in the Cloudflare dashboard before it can be considered safe.

## Deploy staging

1. Add the GitHub repository Actions secret `CLOUDFLARE_API_TOKEN`; never paste its value into chat or source control.
2. Scope the Cloudflare API token to the account and grant `Workers Scripts: Edit`.
3. The workflow pins the public Cloudflare Account ID from the account dashboard; do not create an Actions secret for `CLOUDFLARE_ACCOUNT_ID`.
4. Open Actions → **Cloudflare Free Staging Deploy** → Run workflow from `main`.

The workflow deploys only the isolated `kaizo-coach-core-staging` Worker. It does not connect to Neon or alter production data.

## Production database is deliberately not wired yet

Before connecting any production database:

1. Rotate the Neon database password that was previously stored in the retired Railway environment.
2. Create a separate Neon branch for staging verification; do not test against the live athlete database.
3. Create a Cloudflare Hyperdrive configuration for that branch with query caching disabled. Stale cached ownership or authorization reads are not acceptable.
4. Add the resulting Hyperdrive ID only to the separately reviewed target configuration; never to the free memory-only Staging configuration.
5. Verify persistence, Coach-to-Coach isolation, tenant isolation, audit durability, and read-after-write behavior before considering production.

The Worker uses the Hyperdrive connection string at runtime only when explicitly configured on a reviewed target. It must never be copied into source control or chat. Synchronous PostgreSQL operations are serialized in the Worker entrypoint as required by Cloudflare's Python Workers guidance.

## Free-plan constraints

Cloudflare Workers Free currently allows 100,000 requests/day and 10 ms CPU time per HTTP request. Hyperdrive Free allows 100,000 SQL statements/day. These limits must be measured with the real Coach flows; this Staging setup is not a claim of production readiness.
