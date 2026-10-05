# KAIZO PRODUCTIZATION — PHASE 5
## Epic Design
Date: 2026-10-05
Status: CLOSED — GATE 5A

## 1. Decision
Phase 4 Product Domains are converted into exactly one primary Epic each. Epic IDs are stable product-planning identifiers and do not alter Frozen KAIZO Core logic.

Architecture remains ONE PLATFORM / MULTIPLE EXPERIENCES.
Initial commercial surface remains KAIZO Coach.

## 2. Epic Registry
| Epic ID | Domain | Epic | Primary Surface | Delivery Horizon | Priority |
|---|---|---|---|---|---|
| EPIC-01 | DOM-01 | Athlete Management | Coach | MVP | P0 |
| EPIC-02 | DOM-02 | Coach Workspace | Coach | MVP | P0 |
| EPIC-03 | DOM-03 | Assessment & KPI | Coach | MVP | P0 |
| EPIC-04 | DOM-04 | Problem Diagnosis | Coach | MVP | P0 |
| EPIC-05 | DOM-05 | Decision Support | Coach | MVP | P0 |
| EPIC-06 | DOM-06 | Training Planning | Coach | MVP | P0 |
| EPIC-07 | DOM-07 | Drill Intelligence | Coach | MVP | P0 |
| EPIC-08 | DOM-08 | Progress & Retest | Coach | MVP | P0 |
| EPIC-09 | DOM-09 | Digital Twin | Platform | MVP Platform | P0 |
| EPIC-10 | DOM-10 | Knowledge Management | Platform | MVP Platform | P0 |
| EPIC-11 | DOM-11 | Audit & Governance | Platform | MVP Platform | P0 |
| EPIC-12 | DOM-12 | Safety & Evidence | Platform | MVP Platform | P0 |
| EPIC-13 | DOM-13 | Academy Management | Academy | NEXT | P1 |
| EPIC-14 | DOM-14 | Competition Intelligence | Academy/Coach | LATER | P2 |
| EPIC-15 | DOM-15 | Reporting & Analytics | Academy | NEXT | P1 |

## 3. Epic Charters

### EPIC-01 — Athlete Management
**Outcome:** Coach can create, maintain, search and organize athlete records without duplicating Digital Twin state.
**Capabilities:** CAP-30.
**MVP scope:** athlete profile, roster, status, training group, coach-visible history links.
**Boundary:** product-facing identity/roster only; longitudinal governed state belongs to EPIC-09.

### EPIC-02 — Coach Workspace
**Outcome:** Coach has one operational surface to execute the complete coaching decision cycle.
**Capabilities:** CAP-14 (and workspace orchestration around mapped capabilities).
**MVP scope:** dashboard, athlete/workflow navigation, current priorities, action queue, session entry points.
**Boundary:** workspace orchestrates; it does not own Core intelligence rules.

### EPIC-03 — Assessment & KPI
**Outcome:** Coach can capture structured assessment and KPI evidence that is comparable over time.
**Capabilities:** CAP-25.
**MVP scope:** assessment templates, KPI capture, evidence status, baseline/current state.
**Boundary:** current-state measurement; longitudinal comparison belongs to EPIC-08.

### EPIC-04 — Problem Diagnosis
**Outcome:** Convert assessment evidence into a structured problem statement and diagnosis.
**Capabilities:** CAP-07–CAP-11.
**MVP scope:** problem selection/creation, evidence linkage, cause/context framing, confidence and unresolved-state handling.
**Boundary:** diagnosis frames the problem; it does not select the intervention.

### EPIC-05 — Decision Support
**Outcome:** Help the coach select an appropriate intervention while preserving Coach Final Authority.
**Capabilities:** CAP-12–CAP-16.
**MVP scope:** candidate decisions, rationale/evidence, alternatives, decision record, coach confirmation/override.
**Boundary:** recommendation is not autonomous authority.

### EPIC-06 — Training Planning
**Outcome:** Turn an accepted decision into an executable training plan/session.
**Capabilities:** CAP-19, CAP-21–CAP-23.
**MVP scope:** plan builder, session structure, dosage, progression/regression, constraints.
**Boundary:** executable drill components are owned by EPIC-07.

### EPIC-07 — Drill Intelligence
**Outcome:** Provide executable drill selection and prescription linked to the diagnosed problem and decision.
**Capabilities:** CAP-20.
**MVP scope:** drill library, drill selection, prescription, linkage to problem/decision, execution cues.
**Boundary:** drill is the practice component; session architecture remains EPIC-06.

### EPIC-08 — Progress & Retest
**Outcome:** Close the loop with response capture, retest, comparison and next-state evidence.
**Capabilities:** CAP-24, CAP-26, CAP-27.
**MVP scope:** response logging, retest, before/after comparison, progress state, next-decision trigger.
**Boundary:** validated longitudinal state is reflected into EPIC-09.

### EPIC-09 — Digital Twin
**Outcome:** Maintain governed longitudinal athlete/coaching state for continuity and next decisions.
**Capabilities:** CAP-31.
**MVP Platform scope:** state model, updates, versioning, state retrieval, linkage to decision cycles.
**Boundary:** not a second athlete-profile product.

### EPIC-10 — Knowledge Management
**Outcome:** Provide governed reusable knowledge consumed by product workflows.
**Capabilities:** CAP-01, CAP-03–CAP-05.
**MVP Platform scope:** knowledge records, retrieval, source linkage, lifecycle/status, reusable knowledge units.
**Boundary:** knowledge authority remains separated from product recommendations.

### EPIC-11 — Audit & Governance
**Outcome:** Make material product/system actions traceable and reviewable.
**Capabilities:** CAP-32, CAP-36.
**MVP Platform scope:** audit events, actor/action/time, governance metadata, immutable-ish trace semantics, review hooks.
**Boundary:** audit is evidence of action, not analytics.

### EPIC-12 — Safety & Evidence
**Outcome:** Prevent unsafe/unsupported product behavior and expose evidence quality.
**Capabilities:** CAP-02, CAP-06, CAP-33–CAP-35.
**MVP Platform scope:** safety constraints, evidence requirements, provenance, validation state, escalation/blocking.
**Boundary:** trust service; never bypass Coach Final Authority or Frozen Core governance.

### EPIC-13 — Academy Management
**Outcome:** Extend the validated single-coach workflow to multi-coach academy operations.
**Capabilities:** CAP-17–CAP-18.
**NEXT scope:** academy structure, coach membership/roles, groups, operational coordination.
**Boundary:** starts after Coach workflow is complete and usable.

### EPIC-14 — Competition Intelligence
**Outcome:** Turn reliable progress/retest data into competition-oriented intelligence.
**Capabilities:** CAP-29.
**LATER scope:** competition context, trends, readiness signals, competition analysis.
**Boundary:** deferred until core progress/retest data is reliable.

### EPIC-15 — Reporting & Analytics
**Outcome:** Provide approved operational and performance summaries for coach/academy decisions.
**Capabilities:** CAP-28 and reporting linkage from CAP-30.
**NEXT scope:** athlete progress reports, coach/academy summaries, KPI trends, approved dashboards.
**Boundary:** uses approved data; does not become an audit store or duplicate Digital Twin.

## 4. Cross-Epic Workflow
EPIC-01 Athlete
→ EPIC-03 Assessment/KPI
→ EPIC-04 Diagnosis
→ EPIC-05 Decision
→ EPIC-06 Training
→ EPIC-07 Drill
→ EPIC-08 Response/Retest
→ EPIC-15 Progress/Reporting
→ EPIC-09 Digital Twin
→ next decision.

EPIC-02 is the primary orchestration surface across the workflow.
EPIC-10/11/12 provide shared platform trust and knowledge services.

## 5. Epic Acceptance Rules
1. Every feature has exactly one Primary Epic.
2. Every Epic maps to exactly one Phase-4 Product Domain.
3. Shared platform services may be referenced by features but cannot become hidden duplicate product domains.
4. No feature changes Frozen Core logic without explicit versioned change control.
5. Coach Final Authority remains intact.
6. Productization does not claim market validation; commercial validation remains open.
7. IDs are stable and must not be recycled.

## 6. Gate
GATE 5A = CLOSED.
Next artifact: MASTER FEATURE BACKLOG V1.
