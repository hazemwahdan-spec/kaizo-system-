# P13 — Production-grade RBAC Reference Service

Authorization reference implementation for KAIZO.

Security properties implemented in this phase:
- deny-by-default
- explicit role/permission matrix
- academy/tenant scope enforcement
- server-side authorization
- authorization audit events
- explicit P14 consent boundary

This repository artifact is not itself a production identity provider. Production activation still requires real authentication/credential lifecycle, secret management, TLS, durable audit storage, monitoring, deployment controls, and P14 minor/guardian consent where applicable.