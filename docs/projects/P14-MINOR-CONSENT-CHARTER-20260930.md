# KAIZO P14 — Minor/Child Data & Consent Layer

Date: 2026-09-30
Status: IMPLEMENTATION IN PROGRESS

## Purpose
Provide a separate, explicit consent gate for minor/child data access. P13 RBAC answers who may perform an action; P14 answers whether the child-data access is permitted for the requested scope.

## Scope
- Consent states: pending, active, revoked, expired.
- Guardian relationship and explicit consent scope.
- Academy/tenant scope.
- Resource/action scope; no blanket access from role alone.
- Deny by default when consent is absent or invalid.
- Audit consent changes and child-data authorization decisions.
- Minimize stored data and avoid unnecessary sensitive attributes.

## Required controls
1. No consent -> deny.
2. Pending -> deny.
3. Active + correct guardian + matching academy + matching resource/action scope -> allow.
4. Revoked -> deny.
5. Expired -> deny.
6. Wrong guardian -> deny.
7. Wrong academy -> deny.
8. Consent must be scope-specific.
9. Every decision/change produces an audit event.
10. P13 RBAC remains a separate prerequisite.

## Boundaries
No medical claims, autonomous coaching, athlete selection, scientific validity claims, or modification of KAIZO Core. P05 durable longitudinal storage, production identity proofing, and production security remain separate dependencies.

## Production gate
Reference implementation and independent runtime verification do not equal production activation. Production requires durable secure storage, identity/guardian verification, retention/deletion policy, secure credentials/TLS, monitoring, incident controls, and legal/privacy review appropriate to the deployment jurisdiction.
