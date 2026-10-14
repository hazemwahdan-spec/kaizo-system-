# KAIZO Phase 4 — Durable Tenant/Consent Repository Candidate

**Date:** 2026-10-12  
**Status:** IMPLEMENTATION CANDIDATE — NOT ROUTE-WIRED  
**Requirement:** P4-REQ-011 remains OPEN / NOT PROVEN.

## What this candidate does

- Requires an OIDC-resolver principal marker and a non-empty subject; request-body actor IDs are not accepted as identity.
- Fails closed when PostgreSQL mode is unavailable.
- Requires active tenant membership with an allowed role and an explicit server-side resource-to-tenant binding.
- For child-scoped actions, requires a verified guardian relationship and an active, unexpired consent record for the exact child, tenant, resource type, and action.
- Treats a later consent record or later guardian relationship as superseding an older record, including a revocation or pending state.
- Writes authorization allow/deny audit in the same database transaction. If the audit insert fails, the transaction fails rather than authorizing without an audit record.
- Preserves Coach Final Authority; the returned decision does not authorize autonomous coaching execution.

## Current boundary

The repository is not imported into or enforced by Core API routes. Its result is not yet an authorization control for production requests. It does not create or backfill tenant ownership, establish guardian identity, alter Auth0, apply the migration to production, or write to production.

## Required before merge/activation

1. Confirm canonical resource ownership and parent-child mappings against actual domain tables.
2. Confirm whether guardian relationship and consent rows are mutable current-state records or append-only history; if history, use deterministic ordering/tie-breakers.
3. Add database-backed integration tests for cross-tenant denial, inactive/revoked membership, later guardian revocation, later consent revocation/expiry, and audit failure rollback.
4. Integrate verified OIDC principal dependency into each protected route and resolve ownership from persisted parent chains, not request-body tenant labels.
5. Run actual backend.main:app HTTP tests with missing/invalid token, role mismatch, tenant mismatch, missing/revoked/expired consent, and positive scoped access.
6. Verify production configuration and perform approved controlled tests only after ownership backfill and rollback plan are reviewed.
7. Independent Phase 4 retest must pass before P4-REQ-011 or Phase 4 EXIT can close.

## Evidence

- Schema candidate: backend/migrations/20261011_phase4_tenant_consent.sql
- Repository candidate: backend/phase4_tenant_consent.py
- Unit tests: backend/test_phase4_tenant_consent_repository.py
- CI validates the schema on disposable PostgreSQL; that is not evidence of production migration or route enforcement.
