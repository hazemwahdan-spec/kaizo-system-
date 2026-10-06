# KAIZO COACH — P01

Static coach decision workspace layered above the frozen KAIZO Core API.

Runtime API: https://kaizo-core-engine-production.up.railway.app/api/v1

Exposes existing Core workflows: health, rule evaluation, decision adaptation, decision loop, Digital Twin sync/read, and audit logs. Unvalidated numeric claims remain blocked by Core; Coach Final Authority is explicit in decision-changing requests.

The directory is dependency-free and can be served as a static site with no build step.

## Phase 7 Commercial Surface

The UI now exposes the four governed commercial roles: Academy, Coach, Athlete, and Parent. Navigation is sourced from the Product API. The UI never grants execution authority; server-side Product API/Core governance remains authoritative. Demo identity/tenant headers are development scaffolding only and do not constitute production authentication or RBAC.
