# Phase 4 / Phase 7 — Identity, Academy Tenant and P14 Consent Integration

**Date:** 2026-10-12  
**Branch:** `feat/phase4-identity-tenant-consent-db`  
**Integration base:** `feat/phase4-durable-tenant-consent-repository` (PR #126 retargeted to validate the combined candidate)  
**Pull request:** #126 — draft, not merged  
**Status:** implementation under CI validation; production activation remains gated. Canonical schema is owned by PR #124; this PR must not introduce parallel authorization or consent tables.

## Implemented in this branch

- Product API identity resolution continues to use the existing OIDC principal resolver. The parent progress route now forwards the Authorization bearer token to that resolver rather than dropping it.
- Athlete progress requires a canonical `kaizo_resource_tenant_bindings` row matching resource type `athlete`, athlete ID, and tenant ID.
- Parent progress requires the verified principal to be the parent, the authenticated tenant to match the academy, an active guardian-child-academy link, and active unexpired consent matching `athlete_progress` / `read`.
- Missing assignment/link/consent, revoked or expired consent, and cross-tenant requests are denied. If PostgreSQL-backed authorization is unavailable, the product API returns 503 instead of falling back to caller-supplied headers or in-memory authorization.
- P14 consent service supports durable PostgreSQL consent and audit records and OIDC validation. In-memory behavior is explicitly limited to `KAIZO_IDENTITY_MODE=development`.
- The guardian link is intentionally not created merely by submitting consent. It must be verified through the trusted onboarding process before consent is accepted.

## Required production configuration and data

1. Set `KAIZO_PERSISTENCE_MODE=postgres` and a valid `DATABASE_URL` on both the Core API and P14 consent service.
2. Configure `KAIZO_IDENTITY_MODE=oidc`, `KAIZO_OIDC_ISSUER`, `KAIZO_OIDC_AUDIENCE`, and `KAIZO_OIDC_JWKS_URL` for the relevant services.
3. Confirm academy assignments are written to `kaizo_academy_assignments` with `status='ACTIVE'`.
4. Populate `kaizo_guardian_relationships` only after guardian relationship verification, using the approved onboarding/admin process.
5. Confirm the consent service writes `kaizo_p14_consents` rows and `kaizo_p14_audit_events` events to the same production database used by Core.
6. Run live positive/negative requests against the canonical production hostname using authorized test identities. Do not use real children’s data for these tests.

## Evidence boundary

- Repository changes and automated CI are not live production proof.
- No production environment variables, OIDC settings, or guardian-link data were changed by this branch.
- Do not claim P4-REQ-011 closed until the PR checks pass, the code is reviewed/merged, the production DB configuration is confirmed, and live rejection tests prove cross-tenant, missing-consent and revoked-consent cases.
- The existing Core API decision, assessment, KPI, digital-twin and training-plan routes still require the full route-by-route identity/resource authorization review recorded in `docs/audits/KAIZO_PHASE4_CORE_ROUTE_IDENTITY_INVENTORY_20261011.md`. This PR does not claim that all those Core routes are now protected.


## Follow-up hardening — 2026-10-12

- Removed the second PostgreSQL `consent_change` audit write after the consent upsert. The change event is now recorded once, in the same transaction as the consent mutation; memory-mode development tests retain their in-memory audit behavior.
- Unknown/corrupt persisted consent states are denied as `invalid_consent_state` instead of escaping enum parsing as an unhandled server error.
- Added a separate production-mode CI job that verifies consent write and authorization routes return 503 when no verified identity provider is configured. This is fail-closed evidence only, not proof of successful live OIDC authentication.
- Updated draft PR #126 to record the evidence boundary and its overlap with PR #124. The two candidate branches must be reconciled before merging; neither branch alone is being declared a Phase 4 exit.
- PR #124 and PR #126 overlap on identity, tenant binding and P14 consent. The canonical tables are `kaizo_tenants`, `kaizo_tenant_memberships`, `kaizo_resource_tenant_bindings`, `kaizo_guardian_relationships`, `kaizo_p14_consents`, and `kaizo_p14_audit_events`. Reconcile the code and tests against this schema before merging either PR. CI success and fail-closed tests are not live production proof.
