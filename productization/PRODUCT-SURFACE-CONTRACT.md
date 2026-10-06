# KAIZO Phase 7 — Product Surface Contract

This contract defines the commercial product surface for Academy, Coach, Athlete, and Parent over the frozen Core Engine.

## Non-negotiable governance

- Core Engine remains the decision engine.
- Coach Final Authority remains authoritative.
- Evidence Before Claim remains mandatory.
- Product UI may request decisions, display evidence, record governed outcomes, and expose approved reports.
- Product UI must never authorize execution.
- Client-side hiding is not authorization; server-side RBAC and tenant/resource checks are mandatory.
- Production verification is not claimed by this contract.

## Role surfaces

### Academy
Operational visibility over its academy tenant: dashboard, groups, coaches, athletes, approved reports.

### Coach
Decision and coaching workflow surface: decision cases, adaptation, decision loop, digital twin, audit.

### Athlete
Self-scoped progress, approved feedback, and competition results. Read-only.

### Parent
Explicitly linked athlete progress and approved reports. Read-only.

## Acceptance gate

The surface is acceptable only when runtime tests demonstrate:
1. role-specific access boundaries;
2. tenant isolation;
3. Coach Final Authority;
4. no execution authorization;
5. evidence/approval gates;
6. approved-only reporting.

No production activation is implied until real identity, RBAC, tenant isolation, persistent audit, and live dependencies are verified.
