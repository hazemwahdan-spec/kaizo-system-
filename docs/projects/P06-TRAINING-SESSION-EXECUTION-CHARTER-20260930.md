# P06 — KAIZO Training Session Execution Interface — Charter

Date: 2026-09-30
Status: APPROVED FOR EXECUTION

## Purpose
Provide a mat-ready training-session execution workspace above the frozen KAIZO Core, allowing a coach to prepare, execute, monitor, and close a training unit without replacing Coach Final Authority.

## Scope
- Session identity, date, group, objective and phase.
- Warm-up, technical block, decision/constraint block, randori and cooldown.
- Drill cards with duration, sets/reps, partner system, intensity and coaching cues.
- Live execution checklist.
- KPI capture and retest plan.
- Session completion and audit-oriented summary.
- Explicit HOLD/governance boundaries.
- Local draft state only unless a future persistence project provides an authoritative record.

## Non-scope
- No modification or rebuild of KAIZO Core.
- No production authentication/RBAC; P13 remains the hard gate.
- No minor/guardian consent activation; P14 remains the hard gate.
- No authoritative longitudinal persistence; P05 remains separate.
- No autonomous coaching decisions.
- No medical, scientific or normative claims.
- No video, wearable or competition-provider integration.

## Acceptance Criteria
1. Coach can create and identify a session.
2. Session has structured blocks and executable drills.
3. Coach can mark execution status and capture KPI/retest notes.
4. The interface visibly preserves Coach Final Authority.
5. No unvalidated numeric claim is introduced.
6. Local draft data is clearly non-authoritative.
7. Static runtime is independently testable.
8. Artifact is documented and committed before closure.

## Evidence Plan
- Source/asset discovery.
- Charter and contract.
- Static implementation.
- Automated HTTP/runtime smoke test.
- Independent retest script/check.
- Closure artifact with limitations and commit lineage.

## Governing Rules
Reuse Before Rebuild → Verify Before Reuse → Evidence Before Claim.
Global Governance Baseline remains frozen.
