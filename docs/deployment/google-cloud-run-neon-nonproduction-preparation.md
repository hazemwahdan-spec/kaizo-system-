# KAIZO — Google Cloud Run + Neon non-production preparation

**Status:** preparation only — NOT deployed, NOT production-approved  
**Parent code candidate:** `fix/coach-retire-unscoped-main-api` (security stack after PR #197)  
**Purpose:** prepare a reproducible container and a safe, isolated validation path while Railway is unavailable.

## Decision and boundaries

- Candidate runtime: one Cloud Run service for the FastAPI Core API, built from the repository root using `backend/Dockerfile`.
- Candidate database: a **new, disposable Neon Free project** for non-production only.
- Keep the Coach web UI on its existing frontend host during this preparation. Do not create a second frontend deployment as part of this change.
- Do not connect to, migrate, copy, or modify the existing KAIZO production Neon database.
- Do not configure Auth0 production applications, production secrets, production DNS, or production service settings.
- This PR intentionally contains no deploy workflow, no cloud credentials, no database URL, and no provider-side changes.
- A successful image build is packaging evidence only; it is not runtime, security, persistence, or production acceptance evidence.

## Why this can be low-cost, not guaranteed free

### Cloud Run
Google currently documents a request-based monthly no-cost allowance of 180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million requests. The allowance is aggregated across projects under a billing account. Cloud Run deployment still requires a Cloud Billing account, and usage outside the allowance can be charged. Image builds, Artifact Registry storage, network egress, logging, and adjacent Google Cloud services may have separate charges. Therefore this architecture is **free-tier eligible**, not a promise of a zero bill.

Initial non-production sizing proposal, to be reviewed before any deployment:
- request-based billing;
- minimum instances: 0;
- maximum instances: 1;
- one vCPU and 512 MiB memory;
- no GPU, VPC connector, load balancer, custom domain, or always-on instance;
- configure a budget alert before enabling any billable resource. A budget alert is not a hard spending cap.

Official pricing: https://cloud.google.com/run/pricing

### Neon
Neon's currently published Free plan includes 100 CU-hours per project per month, 1 GB Postgres storage per project, and 5 GB public network transfer per project per month. Compute scales to zero after five minutes of inactivity. Reaching compute or network quotas suspends compute until the next billing period or plan upgrade; storage limits can block writes. These constraints are suitable for isolated development/acceptance testing, not a production durability commitment.

Official limits: https://neon.com/docs/introduction/pro-plan  
Official free-plan FAQ: https://neon.com/docs/introduction/free-plan

## Container contract

- Build context: repository root (`.`), so the shared `productization/` package is included
- Runtime: Python 3.11
- ASGI entrypoint: `main:app`
- Bind address: `0.0.0.0`
- Port: Cloud Run's `PORT` environment variable, defaulting to 8080 for local checks
- Runtime user: unprivileged UID/GID 10001
- Dependencies: pinned in `backend/requirements.txt`
- Root `.dockerignore` excludes local environment files, VCS metadata, caches, and tests from the image context.

Local, non-deploying validation command:

```sh
docker build --pull --file backend/Dockerfile --tag kaizo-core:nonprod-check .
```

No `docker push`, `gcloud run deploy`, or provider mutation is part of this PR.

## Environment contract — configure only after separate approval

Required persistence switch and database variable are confirmed in `backend/persistence.py`:
- `KAIZO_PERSISTENCE_MODE=postgres`
- `DATABASE_URL` — Neon connection string for the **new non-production project only**; store in the provider's secret facility, never in Git or a workflow log.

The exact Auth0/OIDC variable names, issuer, audience, JWKS behavior, and allowed origins must be re-read from the final candidate source and current identity module before creating any Cloud Run revision. Do not infer names or copy production values into this preparation document. Do not disable identity enforcement to make a smoke test pass.

No schema initialization, migration, seed, or ownership backfill is authorized by this preparation. Any disposable-DB schema test must run against the new Neon test project or CI-owned ephemeral PostgreSQL, never against production.

## Required acceptance gates before a deployment can even be proposed

1. Parent security candidate (#197) and its complete Coach dependency chain are reviewed; no deployment from `main` or an unreviewed branch.
2. Container builds reproducibly from the exact reviewed SHA and the app imports/starts without secrets being printed.
3. A dedicated disposable Neon database is created manually by the account owner; its project/region and free-plan limits are recorded. No production DB reuse.
4. Schema/adapter tests, atomic business-write + audit rollback tests, persistence survival tests, and OpenAPI tests pass against the disposable database.
5. Auth0/OIDC configuration is documented from source and independently verified using real signed Bearer tokens; anonymous, invalid issuer/audience, expired token, wrong role, cross-Coach and cross-tenant tests deny access.
6. Coach UI calls only the protected Product API routes; no retired legacy route is re-enabled.
7. Cost review confirms request-based billing, scale-to-zero, max instance limit, budget alert, and no unintended paid ancillary services.
8. A separate, fresh user approval explicitly authorizes a specific non-production deployment. This preparation does not grant that approval.

## Evidence classification

| Evidence | What it proves | What it does not prove |
|---|---|---|
| Docker build passes | Container can be built | App runtime, auth, database, or production |
| Local container smoke test | App starts in local container | Cloud Run identity or network behavior |
| Neon disposable integration tests | Adapter/schema behavior on that test DB | Production data durability |
| Cloud Run non-production live test (future, separately approved) | Exact tested revision and its non-production behavior | Production acceptance |
| Railway / production evidence | Must be collected separately if production target changes | Cannot be inferred from CI or another host |

## Rollback and data safety

For non-production only, rollback means routing test traffic away from the candidate revision and retaining the disposable database for diagnosis. Do not delete or overwrite existing production services, databases, volumes, secrets, or records. Do not point this candidate at the current production Neon endpoint.

**Current state:** source files prepared; no cloud account was accessed, no Neon project was created, no credentials were configured, no image was pushed, and no deployment was performed.
