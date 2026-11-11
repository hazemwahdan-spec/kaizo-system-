# Neon read-only validation

This workflow is intentionally manual and does not run against Railway production.

## One-time setup

1. Use a dedicated **non-production Neon project/database** or an isolated staging branch that contains no production data. Do not branch from production if that would copy production records.
2. Create a PostgreSQL role dedicated to validation. It must not be a superuser and must have no `CREATE` privilege on the database or the `public` schema. Grant only `CONNECT` and the minimum `USAGE` / `SELECT` access needed for metadata checks.
3. In GitHub, open **Settings → Environments** and create `neon-readonly-validation`.
4. Add the connection string for that isolated database as the environment secret `KAIZO_NEON_READONLY_URL`. Never use the Railway production `DATABASE_URL` or any production credential.
5. Run **Actions → Neon Read-Only Connectivity Validation → Run workflow**, and select `NEON_ISOLATED_READ_ONLY` only after confirming the target is isolated.

## What the workflow does

- Requires explicit manual confirmation and the dedicated environment secret.
- Requires TLS and uses an 8-second connection timeout.
- Starts a read-only transaction and a 10-second statement timeout.
- Executes only `SELECT` statements against PostgreSQL metadata and checks whether `kaizo_knowledge_repository` exists.
- Verifies the role is not a superuser and has no database/schema CREATE privilege.
- Rolls back the read-only transaction.

It does not create tables, run migrations, insert/update/delete rows, or connect to Railway. A successful run proves connectivity only to the isolated Neon target supplied in the GitHub environment; it does not prove Railway-to-Neon production connectivity.
