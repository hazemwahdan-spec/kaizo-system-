# KAIZO PRODUCTIZATION — MASTER FEATURE BACKLOG V1
## Phase 5 — Epic → Feature Conversion
Date: 2026-10-05
Status: BASELINE FROZEN — GATE 5B

## 1. Backlog Rules
- Every feature has exactly one Primary Epic.
- Feature IDs are stable: FEAT-001 onward.
- P0 = MVP / platform-critical; P1 = NEXT; P2 = LATER.
- MVP Platform means required infrastructure for the MVP workflow, not a separate customer-facing product.
- Dependencies are expressed by Feature ID where practical.
- This backlog is a product-planning artifact; it does not authorize changes to Frozen KAIZO Core logic.

## 2. Master Feature Backlog

| ID | Primary Epic | Feature | Priority | Horizon | Key Dependency |
|---|---|---|---|---|---|
| FEAT-001 | EPIC-01 | Create athlete profile | P0 | MVP | — |
| FEAT-002 | EPIC-01 | Athlete roster and search | P0 | MVP | FEAT-001 |
| FEAT-003 | EPIC-01 | Training group assignment | P0 | MVP | FEAT-001 |
| FEAT-004 | EPIC-01 | Athlete status/lifecycle | P0 | MVP | FEAT-001 |
| FEAT-005 | EPIC-01 | Athlete-to-decision-cycle history link | P0 | MVP | FEAT-001, FEAT-032 |
| FEAT-006 | EPIC-02 | Coach home dashboard | P0 | MVP | FEAT-001 |
| FEAT-007 | EPIC-02 | Today/current-priority queue | P0 | MVP | FEAT-006 |
| FEAT-008 | EPIC-02 | Athlete workflow navigation | P0 | MVP | FEAT-002 |
| FEAT-009 | EPIC-02 | Decision-cycle workspace | P0 | MVP | FEAT-008, FEAT-014 |
| FEAT-010 | EPIC-02 | Coach action history | P0 | MVP | FEAT-009, FEAT-044 |
| FEAT-011 | EPIC-03 | Assessment template builder | P0 | MVP | — |
| FEAT-012 | EPIC-03 | Record athlete assessment | P0 | MVP | FEAT-001, FEAT-011 |
| FEAT-013 | EPIC-03 | KPI definition and capture | P0 | MVP | FEAT-011 |
| FEAT-014 | EPIC-03 | Assessment evidence attachment | P0 | MVP | FEAT-012, FEAT-047 |
| FEAT-015 | EPIC-03 | Baseline/current-state snapshot | P0 | MVP | FEAT-012, FEAT-013 |
| FEAT-016 | EPIC-04 | Structured problem statement | P0 | MVP | FEAT-012 |
| FEAT-017 | EPIC-04 | Problem library selection | P0 | MVP | FEAT-016 |
| FEAT-018 | EPIC-04 | Cause/context framing | P0 | MVP | FEAT-016 |
| FEAT-019 | EPIC-04 | Evidence-linked diagnosis | P0 | MVP | FEAT-014, FEAT-016 |
| FEAT-020 | EPIC-04 | Diagnosis confidence/unresolved state | P0 | MVP | FEAT-019 |
| FEAT-021 | EPIC-05 | Decision candidate generation | P0 | MVP | FEAT-019, FEAT-052 |
| FEAT-022 | EPIC-05 | Decision rationale and evidence | P0 | MVP | FEAT-021, FEAT-047 |
| FEAT-023 | EPIC-05 | Alternative decision comparison | P0 | MVP | FEAT-021 |
| FEAT-024 | EPIC-05 | Coach confirm/override | P0 | MVP | FEAT-021 |
| FEAT-025 | EPIC-05 | Decision record and outcome intent | P0 | MVP | FEAT-024, FEAT-044 |
| FEAT-026 | EPIC-06 | Training-plan builder | P0 | MVP | FEAT-025 |
| FEAT-027 | EPIC-06 | Session structure and timing | P0 | MVP | FEAT-026 |
| FEAT-028 | EPIC-06 | Dosage/reps/sets prescription | P0 | MVP | FEAT-026 |
| FEAT-029 | EPIC-06 | Progression/regression rules | P0 | MVP | FEAT-026 |
| FEAT-030 | EPIC-06 | Session constraints and notes | P0 | MVP | FEAT-026 |
| FEAT-031 | EPIC-07 | Drill library | P0 | MVP | FEAT-052 |
| FEAT-032 | EPIC-07 | Problem-to-drill linkage | P0 | MVP | FEAT-016, FEAT-031 |
| FEAT-033 | EPIC-07 | Decision-to-drill selection | P0 | MVP | FEAT-025, FEAT-032 |
| FEAT-034 | EPIC-07 | Drill prescription | P0 | MVP | FEAT-033 |
| FEAT-035 | EPIC-07 | Execution cues and checklist | P0 | MVP | FEAT-034 |
| FEAT-036 | EPIC-08 | Training response capture | P0 | MVP | FEAT-027, FEAT-034 |
| FEAT-037 | EPIC-08 | Retest capture | P0 | MVP | FEAT-015, FEAT-036 |
| FEAT-038 | EPIC-08 | Before/after comparison | P0 | MVP | FEAT-037 |
| FEAT-039 | EPIC-08 | Progress state update | P0 | MVP | FEAT-038 |
| FEAT-040 | EPIC-08 | Next-decision trigger | P0 | MVP | FEAT-039, FEAT-052 |
| FEAT-041 | EPIC-09 | Athlete longitudinal state model | P0 | MVP Platform | FEAT-001 |
| FEAT-042 | EPIC-09 | Digital Twin state update | P0 | MVP Platform | FEAT-039 |
| FEAT-043 | EPIC-09 | State version/history | P0 | MVP Platform | FEAT-042 |
| FEAT-044 | EPIC-09 | Decision-cycle state linkage | P0 | MVP Platform | FEAT-025, FEAT-042 |
| FEAT-045 | EPIC-09 | Next-state retrieval for decision | P0 | MVP Platform | FEAT-043, FEAT-044 |
| FEAT-046 | EPIC-10 | Governed knowledge record | P0 | MVP Platform | — |
| FEAT-047 | EPIC-10 | Source/provenance linkage | P0 | MVP Platform | FEAT-046 |
| FEAT-048 | EPIC-10 | Knowledge lifecycle/status | P0 | MVP Platform | FEAT-046 |
| FEAT-049 | EPIC-10 | Knowledge retrieval for workflow | P0 | MVP Platform | FEAT-046, FEAT-048 |
| FEAT-050 | EPIC-10 | Reusable knowledge unit linkage | P0 | MVP Platform | FEAT-049 |
| FEAT-051 | EPIC-11 | Audit event capture | P0 | MVP Platform | — |
| FEAT-052 | EPIC-11 | Actor/action/time trace | P0 | MVP Platform | FEAT-051 |
| FEAT-053 | EPIC-11 | Governance metadata | P0 | MVP Platform | FEAT-051 |
| FEAT-054 | EPIC-11 | Audit query/review | P0 | MVP Platform | FEAT-051 |
| FEAT-055 | EPIC-11 | Product action traceability | P0 | MVP Platform | FEAT-052 |
| FEAT-056 | EPIC-12 | Safety constraint evaluation | P0 | MVP Platform | FEAT-019 |
| FEAT-057 | EPIC-12 | Evidence-quality state | P0 | MVP Platform | FEAT-047 |
| FEAT-058 | EPIC-12 | Provenance visibility | P0 | MVP Platform | FEAT-047 |
| FEAT-059 | EPIC-12 | Unsafe/unsupported action block | P0 | MVP Platform | FEAT-056, FEAT-057 |
| FEAT-060 | EPIC-12 | Escalation and review state | P0 | MVP Platform | FEAT-059, FEAT-054 |
| FEAT-061 | EPIC-13 | Academy entity | P1 | NEXT | FEAT-001 |
| FEAT-062 | EPIC-13 | Coach membership and roles | P1 | NEXT | FEAT-061 |
| FEAT-063 | EPIC-13 | Academy groups | P1 | NEXT | FEAT-061, FEAT-062 |
| FEAT-064 | EPIC-13 | Multi-coach athlete assignment | P1 | NEXT | FEAT-062, FEAT-063 |
| FEAT-065 | EPIC-13 | Academy operational dashboard | P1 | NEXT | FEAT-063, FEAT-064 |
| FEAT-066 | EPIC-14 | Competition event context | P2 | LATER | FEAT-039 |
| FEAT-067 | EPIC-14 | Competition readiness indicators | P2 | LATER | FEAT-066, FEAT-039 |
| FEAT-068 | EPIC-14 | Competition performance capture | P2 | LATER | FEAT-066 |
| FEAT-069 | EPIC-14 | Competition trend analysis | P2 | LATER | FEAT-068, FEAT-039 |
| FEAT-070 | EPIC-14 | Competition-informed next decision | P2 | LATER | FEAT-069, FEAT-040 |
| FEAT-071 | EPIC-15 | Athlete progress report | P1 | NEXT | FEAT-038, FEAT-039 |
| FEAT-072 | EPIC-15 | KPI trend report | P1 | NEXT | FEAT-013, FEAT-039 |
| FEAT-073 | EPIC-15 | Coach performance summary | P1 | NEXT | FEAT-071 |
| FEAT-074 | EPIC-15 | Academy performance dashboard | P1 | NEXT | FEAT-061, FEAT-072 |
| FEAT-075 | EPIC-15 | Approved-data reporting export | P1 | NEXT | FEAT-071, FEAT-054 |

## 3. Backlog Totals
- Epics: 15
- Features: 75
- P0 / MVP + MVP Platform: 60
- P1 / NEXT: 10
- P2 / LATER: 5
- Primary commercial surface: Coach
- Platform trust services: EPIC-09, EPIC-10, EPIC-11, EPIC-12
- Academy expansion: EPIC-13 and EPIC-15
- Deferred intelligence: EPIC-14

## 4. MVP Critical Path
FEAT-001
→ FEAT-012
→ FEAT-016
→ FEAT-019
→ FEAT-021
→ FEAT-024
→ FEAT-026
→ FEAT-033
→ FEAT-036
→ FEAT-037
→ FEAT-038
→ FEAT-039
→ FEAT-040.

Supporting platform path:
FEAT-046/047/049
+ FEAT-051/052
+ FEAT-056/057/059
+ FEAT-041/042/044/045.

Coach Workspace (FEAT-006–010) is the orchestration layer over the critical path.

## 5. Traceability
All 36 Phase-4 capabilities are represented through their owning Epic and feature scope. The Epic-to-Domain relationship is one-to-one. No new Product Domain is introduced in Phase 5.

## 6. Definition of Ready for implementation
A feature may enter implementation only when:
1. acceptance criteria are written;
2. primary domain/epic is confirmed;
3. Core impact is classified as NONE or explicitly version-controlled;
4. required evidence/audit behavior is identified;
5. dependencies are available or deliberately sequenced;
6. security/safety implications are identified where applicable.

## 7. Gate
GATE 5B = CLOSED.
Phase 5 complete.
Next approved step: feature-level decomposition/acceptance criteria and implementation sequencing from the frozen Master Feature Backlog.
