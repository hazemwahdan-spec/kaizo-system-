# KAIZO Persistence Adapter — Design and Boundary Record

Date: 2026-09-30
Branch: feat/kaizo-persistence-adapter

## Purpose

Provide the smallest infrastructure persistence boundary required to move KAIZO from process-memory state toward durable PostgreSQL persistence.

## Governance

- No decision-rule redesign.
- No change to Coach Final Authority.
- No authentication/RBAC bypass.
- No secrets in Git.
- DATABASE_URL is supplied only by deployment environment.
- Existing memory behavior remains the default until PostgreSQL is explicitly enabled.
- Production durability is not claimed until a real managed PostgreSQL instance is connected and restart/redeployment write/read evidence is captured.

## Persisted domains

1. Audit records: kaizo_audit_logs
2. Digital Twin state: kaizo_digital_twin_state
3. Knowledge repository: kaizo_knowledge_repository

## Activation

Set KAIZO_PERSISTENCE_MODE=postgres and provide DATABASE_URL through the deployment environment.

The connection string must never be committed to the repository.

## Evidence gate

This adapter is an implementation artifact, not production proof.

P05 remains BLOCKED until all of the following are demonstrated against a real managed PostgreSQL instance:

1. Schema initialization succeeds.
2. Audit write succeeds.
3. Audit read succeeds.
4. Digital Twin write succeeds.
5. Digital Twin read succeeds.
6. Knowledge write/read succeeds.
7. Data survives service restart or redeployment.
8. Audit remains durable after restart.
9. Production health and controlled decision/retest remain green.
10. P13–P18 are re-evaluated only after the above evidence.

## Rollback

Unset KAIZO_PERSISTENCE_MODE or return it to memory mode and redeploy. No database destructive operation is required.

## Status

IMPLEMENTATION ARTIFACT — NOT PRODUCTION-VERIFIED
