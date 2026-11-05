# KAIZO Phase 4 — Tenant Ownership and Durable P14 Consent Schema

**Date:** 2026-10-11  
**Status:** SCHEMA CANDIDATE — NOT APPLIED TO ANY DATABASE  
**Requirement:** P4-REQ-011 remains OPEN / NOT PROVEN.

## What was added

`backend/migrations/20261011_phase4_tenant_consent.sql` is an additive PostgreSQL migration candidate defining:

- tenant records and explicit subject-to-tenant role memberships;
- one server-side tenant binding per canonical resource type/ID;
- guardian-to-child relationships with explicit verification status;
- scoped P14 consent history (child, guardian subject, tenant, resource type, action, state, expiry);
- durable P14 audit events with reason codes and optional trace IDs.

The migration is intentionally not wired into application startup and has not been run against production or another database. It does not alter existing domain tables, backfill ownership, create users, or grant consent.

## Mandatory integration invariants

1. **Verified identity first:** subject IDs must come from a successfully validated OIDC principal, never from body fields or client-supplied actor headers.
2. **Tenant membership:** authorization requires an active membership for the verified subject, requested role, and server-resolved tenant.
3. **Resource ownership:** resolve resource IDs through canonical persisted parent chains, then require an explicit tenant binding. Missing or conflicting bindings deny access; never infer tenant from request data.
4. **Guardian verification:** child-data consent requires a verified guardian relationship for the same child and tenant. A role claim alone is insufficient.
5. **Consent scope:** require the latest applicable consent for the exact child + guardian + tenant + resource + action. Absent, pending, revoked, expired, invalid, or mismatched consent denies.
6. **Durable audit:** record authorization allow/deny and consent changes with actor subject, reason code, timestamp and trace ID. Audit failures must not silently turn a denied operation into an allow.
7. **Coach Final Authority:** identity and consent gates do not authorize autonomous coaching execution or override coach review.
8. **Safe rollout:** schema application, verified data backfill, real route dependencies, and production activation are separate gated steps. Existing records must not be assigned to a tenant by guesswork.

## Required next work before route wiring

- Confirm Postgres version/extension policy and validate this migration against a disposable PostgreSQL instance.
- Decide canonical resource-type names and map each supported domain record/parent chain to them.
- Approve the source of truth and process for verified academy/tenant ownership and guardian verification.
- Implement a transactional repository/service layer for membership, resource binding, consent history, and audit events.
- Add integration tests against the actual `backend.main:app` with a disposable database, covering unauthenticated access, invalid tokens, role denial, cross-tenant reads/writes, missing bindings, guardian mismatch, all non-active consent states, expiry, audit persistence, and Coach Final Authority.
- Backfill only records whose ownership is established by an authoritative source; quarantine ambiguous records.
- Run an independent retest and obtain explicit production activation authorization before changing provider/runtime configuration.

## Evidence boundary

This file and migration are design/code artifacts only. They are not evidence of database application, durable runtime behavior, route enforcement, production activation, legal compliance, or Phase 4 exit.
