# KAIZO — Railway Constraint Resolution Report — 2026-09-30

## Executive finding

The Railway problem has two separate constraints:

1. Railway capacity/plan: the current project has five production services. Current Railway pricing says Free/Trial allows five services during trial, then three; Hobby allows fifty. Railway supports PostgreSQL as a native database service. A sixth service is therefore blocked on the current Free/Trial capacity unless the workspace has sufficient plan capacity.
2. Connector permission: the current ChatGPT Railway connector can list the user's projects, but project-level status access for the KAIZO project is rejected with "You don't have the required role (viewer) on this resource." No mutation was attempted through this restricted path.

## Critical source-code finding

The current GitHub main branch was inspected directly.

backend/main.py currently stores:
- AUDIT_LOGS in an in-memory Python list.
- DIGITAL_TWIN_STATE in an in-memory Python dictionary.
- KNOWLEDGE_REPOSITORY in an in-memory Python dictionary.

backend/requirements.txt currently contains FastAPI, Uvicorn and Pydantic only. No PostgreSQL driver, SQLAlchemy, asyncpg, psycopg, or database abstraction was found in the current repository search.

### Consequence

Provisioning PostgreSQL alone would NOT create durable KAIZO persistence.

A minimal persistence adapter/schema implementation is required before P05 can be honestly closed. This is an infrastructure/persistence layer change, not a Core Engine decision-logic rebuild, but it must be separately evidenced and reviewed.

## Railway recovery paths

### R1 — Keep Railway, add native PostgreSQL

Existing Railway services + Railway PostgreSQL + minimal persistence adapter.

Status:
- Architecture: PASS
- Core Engine migration: LOW
- Service count: PASS after sufficient plan capacity
- Durable DB: PASS after actual provisioning and persistence verification
- Current connector execution: BLOCKED by project role

### R2 — Railway compute + external PostgreSQL

Existing Railway services + external managed PostgreSQL + minimal persistence adapter.

Candidates: Neon, Supabase, Render PostgreSQL, DigitalOcean Managed PostgreSQL, Google Cloud SQL.

### R3 — Render compute + Render PostgreSQL

Technically viable on paid infrastructure. Render Free Postgres is not acceptable for durable production because its official documentation states that Free Postgres expires after 30 days and has no backups.

### R4 — Railway compute + Neon PostgreSQL

Technically attractive for low-cost development/early production. Neon Free currently provides 0.5 GB per project and limited compute/recovery features; final production durability must be evaluated against the required backup/HA standard.

### R5 — Railway compute + Supabase PostgreSQL

Technically viable. Supabase Free includes PostgreSQL but excludes automatic backups and point-in-time recovery; stronger production durability requires an appropriate paid tier.

### R6 — Cloud SQL / DigitalOcean

Strong managed PostgreSQL options with higher operational/cost overhead. DigitalOcean managed PostgreSQL currently starts at $15/month for a single-node cluster. Google Cloud SQL provides managed PostgreSQL and new customers may receive $300 in credits, with normal production billing based on compute, storage and networking.

## Comparative matrix

| Path | Railway dependency | DB persistence | Cost barrier | Core impact | Current blocker |
|---|---|---|---|---|---|
| R1 Railway + native PG | High | PASS after adapter | Billing/plan | Low | Railway project permission + plan |
| R2 Railway + external PG | Medium | PASS after adapter | Provider account | Low | Provider provisioning |
| R3 Render + Render PG | Low | PASS on paid plan | Billing | Medium | Existing Render billing constraint |
| R4 Railway + Neon | Medium | PARTIAL on Free / stronger paid | Low initially | Low | Provider account + adapter |
| R5 Railway + Supabase | Medium | PARTIAL on Free / stronger paid | Low initially | Low | Provider account + adapter |
| R6 Cloud SQL / DO | Low/Medium | PASS | Paid | Medium | Account/billing |

## Rejected shortcuts

- SQLite as production substitute — REJECTED
- JSON/filesystem persistence — REJECTED
- In-memory audit as durable audit — REJECTED
- self-managed PostgreSQL without durable backup/volume evidence — REJECTED
- deleting/reusing an existing production service to create a database — REJECTED
- declaring P05 closed merely because PostgreSQL exists — REJECTED

## Minimum viable production infrastructure

Existing KAIZO Core Engine
→ minimal PostgreSQL persistence adapter
→ managed PostgreSQL
→ durable audit tables
→ real write/read verification
→ P13–P18 activation evidence

No Core Engine decision logic needs to be rebuilt.

## Immediate Railway resolution

1. Obtain Owner/Editor access to the KAIZO Railway project for the operator/tool that must provision infrastructure.
2. Upgrade the Railway workspace/project to a tier that permits the required service count if the current Free/Trial service cap blocks a sixth service.
3. Add Railway PostgreSQL.
4. Add only the minimum required environment configuration.
5. Implement the persistence adapter without changing decision logic.
6. Deploy.
7. Verify durable write/read across restart/redeployment.
8. Verify durable audit persistence.
9. Re-run P13–P18 evidence.
10. Reconcile P05 and final readiness.

## Alternative if Railway billing/access remains blocked

Use Railway existing compute + Neon or Supabase PostgreSQL.

This removes the need for a sixth Railway service while preserving the existing Railway production surfaces.

The application still requires the same minimal persistence adapter.

## Current execution boundary

The current ChatGPT Railway connector can enumerate the account's projects but cannot access the KAIZO project with the required viewer role. Therefore it cannot safely provision or inspect the project's infrastructure from this session.

No destructive Railway action was taken.

## Governance preserved

- Reuse Before Rebuild
- Verify Before Reuse
- Evidence Before Claim
- No Core Engine rebuild
- No SQLite production substitute
- No destructive service repurposing
- Coach Final Authority preserved
- Human Oversight preserved
- AI remains non-authoritative

Date: 2026-09-30
