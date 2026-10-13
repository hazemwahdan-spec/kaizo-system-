# KAIZO Phase 4 — Identity Store / Consent Schema Contract Mismatch

**Date:** 2026-10-12  
**Status:** BLOCKER — DO NOT MERGE/ACTIVATE UNTIL RECONCILED  
**Requirement:** P4-REQ-011 OPEN / NOT PROVEN

## Evidence reviewed

- Runtime adapter: `backend/phase4_identity_store.py` on `feat/phase4-identity-enforcement-gate`.
- Candidate migration: `backend/migrations/20261011_phase4_tenant_consent.sql` on PR #123 (`feat/phase4-tenant-consent-schema`).
- PR #122 and PR #123 are separate open branches; the candidate migration is not assumed to exist on PR #122 or in any live database.

## Contract mismatches

| Concern | Runtime adapter expects | Candidate migration defines |
|---|---|---|
| Membership table | `kaizo_tenant_memberships` columns `membership_id, actor_id, academy_id, role, status, version, resource_owner_id` | `kaizo_tenant_memberships` columns `membership_id, tenant_id, subject_id, role, status`; no `version` or `resource_owner_id` |
| Membership status | Compares lowercase `active` | Constraint permits uppercase `ACTIVE, SUSPENDED, REVOKED` |
| Guardian table | `child_id, guardian_actor_id, academy_id, verification_status, version, verified_by, verified_at` | `child_resource_id, guardian_subject_id, tenant_id, verification_status, verified_by_subject, verified_at`; no `version` |
| Consent table | `kaizo_child_consents`, with `child_id, guardian_actor_id, academy_id, resource, action, state, version` | `kaizo_p14_consents`, with `child_resource_id, guardian_subject_id, tenant_id, resource_type, action, state, created_at`; no `version` |
| Audit table | `kaizo_authorization_audit` | `kaizo_p14_audit_events`, with a different column contract |

## Required corrective work

1. Select one canonical schema/API contract and align the migration, repository adapter, and tests in one reviewed change set.
2. Define latest-record semantics deterministically. If append-only history is retained, use a stable ordering (timestamp plus unique ID) and test active → revoked, pending, expired, and mismatched scopes.
3. Verify status normalization and expiry behavior against the actual schema.
4. Run migration and repository integration tests on disposable PostgreSQL, including transaction rollback and audit write failure behavior.
5. Only after schema/repository agreement, add actual-app route authorization using verified OIDC identity plus server-loaded resource ownership and scoped consent.
6. Do not apply this candidate migration to production or activate the identity gate as part of this change.

## Evidence boundary

This is a source-level contract review. It is not evidence that the migration has been applied, that production uses these tables, or that any route is protected. Phase 4 exit remains blocked.
