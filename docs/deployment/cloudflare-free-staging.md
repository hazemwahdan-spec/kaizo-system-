# Cloudflare Free Staging Runtime

## Safety boundary

- The isolated Worker is named `kaizo-coach-core-staging`; the existing `kaizo-system` Worker is a separate Production service.
- This Worker is intentionally memory-only. It has no Hyperdrive binding and no database credentials. It may serve the static Coach UI and basic Core surface, but it is **not** a durable Coach API: verified Coach Product API requests fail closed with HTTP 503 until a separate Staging API is connected to allowlisted PostgreSQL.
- Do not use the memory-only Worker for real athlete records, PostgreSQL persistence proof, audit durability proof, or Auth0 cross-scope acceptance.
- OIDC remains enabled. Actor, role, tenant, and ownership are derived from the verified token and server-side ownership records; caller-supplied identity headers are not trusted.
- Cloudflare's Git-connected status for `kaizo-system` refers to the existing Production Worker. A failed build there is not a Staging deployment or Staging acceptance result.

## Cloudflare Git-connected build boundary

The repository-root `wrangler.jsonc` is intentionally pinned to `kaizo-coach-core-staging`. It must not be renamed to `kaizo-system` to make the existing Production Git integration pass: that would point this Staging-only, memory-only configuration at the Production Worker.

Cloudflare Workers Builds requires the Worker name in the dashboard to match the `name` in the Wrangler configuration. Therefore:

- The existing Production Worker `kaizo-system` must use its own Production configuration/repository root, or have this repository-root Staging build integration disconnected.
- If Git-connected builds are desired for this configuration, connect them to the Staging Worker `kaizo-coach-core-staging`.
- The manual GitHub Actions workflow below is a separate Staging deployment path; it does not require the Production Worker Git integration.

Do not treat a failed `Workers Builds: kaizo-system` check as evidence that the isolated Staging Worker was deployed or that Staging runtime acceptance failed.

## Deploy the isolated memory-only Worker

1. Configure the GitHub repository Actions secret named `CLOUDFLARE_API_TOKEN` with the **full token secret value** copied once from Cloudflare. The Cloudflare display label (for example, `KAIZO-CLOUDFLARE-DEPLOY`) is not the GitHub secret name.
2. Use an active token with Account-level Workers Scripts Edit permission. The workflow first verifies an Account API token at `/accounts/{account_id}/tokens/verify`, then falls back to the User API token verification endpoint if needed. It next checks access to the account's Worker scripts.
3. Do **not** create a `CLOUDFLARE_ACCOUNT_ID` secret; the public Account ID is pinned in the workflow. Never paste token values into chat, logs, issues, or source control.
4. Open Actions → **Cloudflare Free Memory-only Staging Deploy** → Run workflow. Run it from `main` or an approved `fix/coach-staging-*` branch.
5. The workflow validates the isolated Worker name and memory-only settings, checks the import guard, runs a Wrangler dry-run, and only then deploys `kaizo-coach-core-staging`.

A token beginning with `cfat_` is an Account API token; one beginning with `cfut_` is a User API token. If both verification endpoints return HTTP 401, replace the GitHub secret with the full, active token value. Do not share the token itself.

## Durable Coach Staging is a separate target

The memory-only Worker is not the target for the durable Coach acceptance workflows.

- **Schema preparation:** `.github/workflows/coach-scoped-evidence-staging-schema.yml` requires GitHub Environment `staging`, secret `KAIZO_STAGING_DATABASE_URL`, and trusted variables `KAIZO_STAGING_DB_HOST` and `KAIZO_PRODUCTION_DB_HOST`. It verifies the exact Staging database target and adds only the four Coach-scoped evidence tables; it does not call repository-wide `persistence.initialize()`.
- **Auth0 live proof:** `.github/workflows/coach-auth0-staging-live-proof.yml` uses the trusted `KAIZO_STAGING_API_URL` variable and repository/environment OIDC test secrets. It performs GET-only authorization checks. Its API target must be a separate Staging API connected to the same allowlisted PostgreSQL database.
- Before either workflow is run, confirm the exact Staging API host and database host, configure the required environment variables/secrets without exposing their values, and obtain explicit approval for that Staging target.

## Production remains separate

No Production database, Auth0 Production settings, Cloudflare Production Worker, or Railway configuration is changed by these Staging workflows. Production deployment identity, Health, OpenAPI, and live security checks remain a separate acceptance gate.
