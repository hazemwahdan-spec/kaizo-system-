# P13 — Production-grade Role & Permission System Charter

## Purpose
Establish the authorization boundary required before KAIZO multi-user production surfaces become active.

## Design
- Deny by default.
- Explicit role-to-permission matrix.
- Tenant/academy scope is mandatory for protected resources.
- Authentication identity is distinct from authorization role.
- Minor/guardian consent is a separate P14 gate.
- Every authorization decision is auditable.
- No client-side permission check is authoritative.
- Coach Final Authority is preserved; RBAC does not create coaching authority.
- System/service identities are explicit, not implicit.

## Roles
- coach
- technical_director
- academy_director
- academy_admin
- athlete
- parent_guardian
- researcher
- system

## Runtime boundary
This phase implements and independently tests the authorization reference service. It is not declared production-activated until deployed with a real identity provider/credential lifecycle, durable audit storage, secret management, TLS, operational monitoring, and P14 consent controls where minors are involved.

## Acceptance
1. Deny unknown role/action by default.
2. Enforce explicit role permissions.
3. Enforce academy scope.
4. Prevent cross-academy access.
5. Produce authorization audit events.
6. Test protected and denied paths independently.
7. Preserve separation from P14 consent.
8. Commit closure evidence.
