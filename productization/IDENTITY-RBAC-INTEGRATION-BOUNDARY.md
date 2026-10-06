# KAIZO Phase 7 — Identity / RBAC Integration Boundary

This contract defines the security boundary between product surfaces and the frozen Core Engine.

## Rules
- Authentication is required before protected product access.
- Authorization is enforced server-side; UI visibility is never authorization.
- Academy access is tenant-scoped.
- Coach access is limited to assigned/authorized athletes and cases.
- Athlete access is self-scoped.
- Parent access requires an explicit athlete relationship.
- Privileged actions must create an audit event.
- No role can execute training autonomously or bypass Coach Final Authority.
- Cross-tenant access is denied.
- Unapproved data export is denied.

## Production Gate
This is a boundary contract, not proof of production identity/RBAC. Production activation remains gated until real authentication, RBAC, tenant isolation, resource ownership, audit persistence, and live dependency verification are evidenced.
