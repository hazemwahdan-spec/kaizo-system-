# KAIZO Phase 7 — Execution Foundation

## Baseline
- Frozen Phase 5 baseline: `e089879c24ccfa87b30f9644f67e69bd8c12c629`
- Phase 5 remains immutable by policy.
- Phase 7 is a new change set for product execution.

## Product boundary
KAIZO becomes one product surface over the preserved Core Engine. The commercial surface serves four explicit roles:
1. Academy
2. Coach
3. Athlete
4. Parent

The Core Engine remains the decision engine and does not become a self-authorizing actor.

## Non-negotiable invariants
- Coach Final Authority is preserved.
- Human Oversight is preserved.
- Evidence Before Claim is preserved.
- Unsupported/unsafe states remain HOLD.
- Product UI may request decisions, display evidence, record outcomes, and export approved data; it may not authorize execution.
- No role receives implicit execution authority.
- Phase 5 frozen artifacts are not rewritten.

## Phase 7 execution sequence
1. Product role contracts.
2. Product navigation/surface contracts.
3. Identity/RBAC integration boundary.
4. Commercial tenancy boundary.
5. Product runtime integration against the frozen Core APIs.
6. Acceptance/E2E evidence.
7. Production activation only after real dependency verification.

This commit implements step 1 only and establishes the contract consumed by subsequent Phase 7 work.
