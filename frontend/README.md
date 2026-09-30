# KAIZO COACH — P01

Static coach decision workspace layered above the frozen KAIZO Core API.

Runtime API: https://kaizo-core-engine-production.up.railway.app/api/v1

Exposes existing Core workflows: health, rule evaluation, decision adaptation, decision loop, Digital Twin sync/read, and audit logs. Unvalidated numeric claims remain blocked by Core; Coach Final Authority is explicit in decision-changing requests.

The directory is dependency-free and can be served as a static site with no build step.