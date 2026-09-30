# KAIZO P05 — Longitudinal Athlete Record

Persistent athlete history service above the frozen KAIZO Core.

## Event model
The record uses an append-only event ledger. Supported event types include:
training, assessment, goal, observation, decision, intervention, kpi_measurement, retest, competition, self_reflection, milestone.

## Governance
- No Core Engine modification.
- Actor role and academy scope are required on every protected request.
- Minor records require an active consent state; P14 remains the authoritative activation gate.
- Production authentication/RBAC remains P13.
- P15 remains responsible for broader scalable analytics infrastructure.
- The service does not make autonomous coaching decisions.

## Runtime
Requires DATABASE_URL.
GET /health verifies PostgreSQL reachability.
GET /api/v1/record-contract exposes the governed record contract.
