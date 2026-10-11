# Phase 4 Digital Brain — Traceability & Design Red-Team Plan

**Date:** 2026-10-11  
**Master board step:** 6 — Phase 4 Entry Gate  
**Status:** TRACEABILITY BASELINE DRAFTED; DESIGN REVIEW RECORDED; GATE NOT OPEN  
**Boundary:** This is a planned requirement-to-test matrix and internal design-level red-team review. It is not runtime test evidence or independent external sign-off.

## 1. Requirement traceability matrix

| Requirement ID | Requirement | Existing source/evidence to reuse | Required Phase 4 acceptance / negative test | Current status |
|---|---|---|---|---|
| P4-REQ-001 | Every input has source, version, evidence status and provenance | Core Reference; Reference Library; E0–E6/R1–R5 concepts | Missing/unknown source must produce HOLD; stale or conflicting versions must not silently pass | PLAN REQUIRED; no Phase 4-specific test |
| P4-REQ-002 | Only approved/versioned rules may drive a decision | Core Reference closure decision; frozen Core rules | E0/unvalidated numeric claim is rejected as a decision-driving rule; unknown rule version fails closed | PLAN REQUIRED |
| P4-REQ-003 | Decision follows canonical decision cycle | Decision Engine v1.0 | Required inputs missing at any step must stop/hold with explicit reason | EXISTING CANONICAL PROCESS; phase-specific test missing |
| P4-REQ-004 | Alternatives include rationale and linked evidence | FEAT-021 candidate generation; FEAT-022 rationale/evidence; FEAT-023 comparison | No candidate may be shown as evidence-backed if its source link is absent | Existing feature tests; Phase 4 mapping missing |
| P4-REQ-005 | Coach confirmation/override is authoritative | FEAT-024 coach confirm/override | No intervention/plan becomes approved without coach action; override retains history | Existing feature test; Phase 4 mapping missing |
| P4-REQ-006 | Decisions and overrides are auditable | FEAT-025 decision record; FEAT-046 audit spine | Attempted audit mutation/deletion or missing required event must fail/alert | Existing feature tests; Phase 4 mapping missing |
| P4-REQ-007 | Plan generation remains a proposal pending coach confirmation | FEAT-026 training plan; FEAT-027 session structure/timing | No automatic execution after plan generation; unauthorized acceptance is denied | Existing feature tests; Phase 4 mapping missing |
| P4-REQ-008 | Intervention → KPI → retest loop preserves baseline and outcome linkage | FEAT-011 measurements; FEAT-012 assessment; FEAT-013 KPI; FEAT-014 evidence attachment; FEAT-015 state snapshot | Missing baseline or KPI must not be fabricated; retest must preserve lineage | Existing feature tests; Phase 4 mapping missing |
| P4-REQ-009 | Validation/safety guardrails block unsafe or unsupported paths | FEAT-056 safety/evidence guardrails | Invalid, incomplete, contradictory or unsafe request returns HOLD/deny rather than confident unsupported output | Existing feature test; Phase 4 mapping missing |
| P4-REQ-010 | Persistence is durable and linked to audit events | Persistence Adapter Validation workflow | Reopen/read-back verifies decision, evidence, state and audit record; test is not production proof | CI integration tests exist; live production proof missing |
| P4-REQ-011 | Role, tenant and consent boundaries are respected where applicable | Identity/RBAC workflow; P13/P14 activation boundaries | Unauthorized role, cross-tenant read/write, missing approval or required consent is denied | Separate runtime evidence exists; Phase 4-specific mapping missing |
| P4-REQ-012 | No autonomous decision/intervention bypasses Coach Final Authority | Frozen Core governance; FEAT-024; safety guardrails | Static and behavioral checks reject execution without authorized coach approval | Governance principle exists; Phase 4-specific red-team evidence missing |

## 2. Proposed Phase 4 test suites

These are test names/contracts to implement or map after the entry gate is approved. They are not claimed as executed tests.

- P4-T01 — input provenance and version validation
- P4-T02 — approved-rule selection and E0 numeric claim blocking
- P4-T03 — canonical decision-cycle completeness
- P4-T04 — recommendation evidence/rationale integrity
- P4-T05 — coach confirm/override and immutable history
- P4-T06 — audit event completeness and tamper resistance
- P4-T07 — planning proposal requires coach approval
- P4-T08 — baseline/KPI/retest lineage
- P4-T09 — invalid, stale, conflicting and unsafe input HOLD paths
- P4-T10 — durable persistence round-trip with audit linkage
- P4-T11 — role/tenant/consent negative paths where applicable
- P4-T12 — no autonomous execution bypass / Coach Final Authority

Acceptance requires exact run URL, commit SHA, output artifact, negative-path result and independent retest reference for each applicable test. Existing feature tests may be reused but must be mapped to the Phase 4 requirement and must not be relabelled as Phase 4 tests without that trace.

## 3. Design-level red-team checklist

| Threat / failure mode | Required disposition | Review result for the current package |
|---|---|---|
| Unvalidated E0 numeric claim drives a recommendation | Block/HOLD | Guardrail specified; runtime proof pending |
| Missing provenance is presented as verified evidence | Block/HOLD | Guardrail specified; runtime proof pending |
| Recommendation automatically triggers intervention | Deny unless coach confirms | Coach authority boundary explicit; runtime proof pending |
| Coach override erases the original recommendation | Preserve both original and override in audit | Required; implementation/test mapping pending |
| Cross-tenant or unauthorized access returns athlete data | Deny and audit | Required; Phase 4-specific test pending |
| Required consent/approval is bypassed | Deny | Required where applicable; live proof pending |
| Runtime evidence is promoted to human-expert validation | Prohibit | Governance boundary explicit |
| T-001–T-014 is represented as a complete global vocabulary | Prohibit; preserve scoped claim | Scope boundary explicit |
| Historical OIDC HTTP 200 is treated as current production health | Prohibit | Production target and current live evidence remain unresolved |
| Core Engine v2.0 proposal is silently promoted to canonical architecture | Prohibit | Version authority boundary explicit |
| Productization Gate 4 is treated as master-board Phase 4 PASS | Prohibit | Taxonomy boundary explicit |

### Design-review disposition

The current written package explicitly addresses the major governance and scope-confusion threats above. This is an internal design-level review only. It does **not** constitute an independent red-team sign-off, and it does not prove runtime behavior.

## 4. Gate readiness summary

| Gate component | Status |
|---|---|
| Reconciled roadmap | PASS |
| Source-bounded Phase 4 charter/dependency model | DRAFTED |
| Requirement-to-test traceability | DRAFTED; needs implementation/test-run links |
| Design-level red-team checklist | DRAFTED; internal review only |
| Independent red-team / retest | NOT DONE |
| Explicit Phase 4 owner/approver decision | NOT RECORDED |
| Gate freeze / PASS decision | NOT RECORDED |
| Current production target | OWNER DECISION STILL OPEN for later live proof |

## 5. Step 6 decision

**PHASE 4 ENTRY GATE REMAINS NOT OPEN.**

The traceability baseline and design-level red-team plan are now documented. The remaining gate blockers are:
1. Map the proposed requirements to a formally approved Phase 4 scope/contract.
2. Complete the independent gate review/negative-path plan with an accountable reviewer.
3. Record the explicit owner/approver decision and a separate gate PASS artifact.
4. Preserve the canonical production target as an owner decision for later deployment readiness/proof.

No Phase 4 implementation is authorized until the gate PASS is explicit. No runtime tests are claimed from this planning document.
