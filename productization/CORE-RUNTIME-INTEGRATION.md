# KAIZO Phase 7 — Core Runtime Integration

## Purpose
Connect the commercial product surface to the frozen Phase 5 Core Engine without changing Core authority boundaries.

## Runtime Contract
The product may request decisions, submit evidence, record interventions and outcomes, display Core results, and export approved records.

The product MUST NOT:
- authorize execution;
- bypass evidence gates;
- override Coach Final Authority;
- bypass safety holds;
- access another tenant's resources.

## Runtime Sequence
1. Authenticate the actor.
2. Resolve tenant and role.
3. Enforce server-side resource scope.
4. Submit the permitted Core operation.
5. Receive the Core decision/evidence response.
6. Require human Coach review where the contract requires it.
7. Record the outcome.
8. Audit privileged mutations.

## Frozen-Core Rule
Phase 5 remains the immutable baseline. Phase 7 integrates against its existing APIs and contracts; it does not silently rewrite or weaken them.

## Evidence Gate
This document is an integration contract, not production proof. Production verification requires live runtime evidence, authorization-negative tests, tenant-isolation tests, persistence evidence, and end-to-end acceptance.
