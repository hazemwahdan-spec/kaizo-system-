# KAIZO Phase 7 — Commercial Tenancy / Multi-Academy Boundary

## Objective
Allow multiple academies to use the commercial product while preventing unauthorized cross-academy data access.

## Isolation
Every protected commercial resource is tenant-scoped. The default cross-tenant decision is DENY.

## Role Scope
- Academy: tenant-wide operational scope.
- Coach: tenant scope plus assigned/authorized resources.
- Athlete: own resources within the tenant.
- Parent: explicitly linked athletes within the tenant.

## Authorization Order
1. Authenticate identity.
2. Resolve tenant membership.
3. Verify role permission.
4. Verify resource ownership/scope.
5. Verify Coach Final Authority where applicable.
6. Record an audit event for privileged actions.

## Denials
Cross-tenant access, unauthorized resource access, unapproved exports, safety override, evidence bypass, and autonomous execution are denied.

## Gate
This contract defines the commercial boundary only. Production tenancy isolation is NOT claimed until live database/API enforcement and runtime cross-tenant negative tests provide evidence.
