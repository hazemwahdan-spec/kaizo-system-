# KAIZO PRODUCTIZATION — PHASE 4
## Product Domain Design
Date: 2026-10-05
Status: CLOSED — GATE 4

## 1. Decision
Recommended architecture: ONE PLATFORM / MULTIPLE EXPERIENCES.
Initial commercial experience: KAIZO Coach.
Academy is the first expansion layer. Athlete/Parent/Enterprise are later experiences.

## 2. Product Domains
| ID | Domain | Primary Product | Primary Capability | Owner | Status |
|---|---|---|---|---|---|
| DOM-01 | Athlete Management | Coach | CAP-30 | Coach Product | EXTEND |
| DOM-02 | Coach Workspace | Coach | CAP-14 | Coach Product | BUILD |
| DOM-03 | Assessment & KPI | Coach | CAP-25 | Measurement | BUILD/EXTEND |
| DOM-04 | Problem Diagnosis | Coach | CAP-07 | Intelligence | EXTEND |
| DOM-05 | Decision Support | Coach | CAP-14 | Intelligence | EXTEND |
| DOM-06 | Training Planning | Coach | CAP-19 | Training | BUILD |
| DOM-07 | Drill Intelligence | Coach | CAP-20 | Training | BUILD |
| DOM-08 | Progress & Retest | Coach | CAP-27 | Measurement | BUILD/EXTEND |
| DOM-09 | Digital Twin | Platform | CAP-31 | Core | REUSE |
| DOM-10 | Knowledge Management | Platform | CAP-01 | Knowledge | REUSE/EXTEND |
| DOM-11 | Audit & Governance | Platform | CAP-32 | Governance | REUSE |
| DOM-12 | Safety & Evidence | Platform | CAP-33/34/35 | Governance | REUSE |
| DOM-13 | Academy Management | Academy | CAP-17/18 | Academy | NEXT |
| DOM-14 | Competition Intelligence | Academy/Coach | CAP-29 | Intelligence | LATER |
| DOM-15 | Reporting & Analytics | Academy | CAP-28/30 | Analytics | NEXT |

## 3. Boundary Rules
1. Coach Workspace is the primary commercial surface.
2. Assessment, Diagnosis, Decision, Training and Measurement form one connected workflow; they are domains, not separate products.
3. Digital Twin, Audit, Safety and Evidence are platform trust services, not standalone customer products.
4. Knowledge is a shared platform service consumed by Coach and Academy experiences.
5. Academy Management begins only after the single-coach workflow is complete and usable.
6. Athlete/Parent views consume approved data and never bypass Coach Final Authority.
7. Competition Intelligence is deferred until core progress/retest data is reliable.
8. No domain may duplicate Frozen Core logic.
9. Product UI/API may extend Core behavior only through versioned change control.
10. Every future feature must map to exactly one primary domain and may reference shared platform domains.

## 4. Capability-to-Domain Mapping
KNOWLEDGE: CAP-01→DOM-10; CAP-02→DOM-12; CAP-03→DOM-10; CAP-04→DOM-10; CAP-05→DOM-10; CAP-06→DOM-12.
ANALYSIS: CAP-07→DOM-04; CAP-08→DOM-04; CAP-09→DOM-04; CAP-10→DOM-04; CAP-11→DOM-04; CAP-12→DOM-05.
DECISION: CAP-13→DOM-05; CAP-14→DOM-05; CAP-15→DOM-05; CAP-16→DOM-05; CAP-17→DOM-13; CAP-18→DOM-13.
TRAINING: CAP-19→DOM-06; CAP-20→DOM-07; CAP-21→DOM-06; CAP-22→DOM-06; CAP-23→DOM-06; CAP-24→DOM-08.
MEASUREMENT: CAP-25→DOM-03; CAP-26→DOM-08; CAP-27→DOM-08; CAP-28→DOM-15; CAP-29→DOM-14; CAP-30→DOM-01.
SYSTEM: CAP-31→DOM-09; CAP-32→DOM-11; CAP-33→DOM-12; CAP-34→DOM-12; CAP-35→DOM-12; CAP-36→DOM-11.

## 5. Critical Product Flow
DOM-01 Athlete
→ DOM-03 Assessment/KPI
→ DOM-04 Diagnosis
→ DOM-05 Decision
→ DOM-06 Training
→ DOM-07 Drill
→ DOM-08 Response/Retest
→ DOM-15 Progress
→ DOM-09 Digital Twin
→ next decision.

## 6. MVP Boundary
MVP domains:
DOM-01, DOM-02, DOM-03, DOM-04, DOM-05, DOM-06, DOM-07, DOM-08, plus DOM-09/11/12 as platform services.

NEXT:
DOM-13, DOM-15.

LATER:
DOM-14 and independent Athlete/Parent/Enterprise experiences.

## 7. Duplication Review
No blocking domain duplication identified.
Potential overlap is controlled by boundary rules:
- Assessment vs Progress: Assessment records current state; Progress compares validated states over time.
- Diagnosis vs Decision: Diagnosis identifies/frames the problem; Decision selects the intervention.
- Training vs Drill: Training defines the session/action; Drill defines the executable practice component.
- Digital Twin vs Athlete Management: Athlete Management is the product-facing roster/profile; Digital Twin is the governed longitudinal state.
- Audit/Governance vs Analytics: Audit records evidence and traceability; Analytics summarizes approved data.

## 8. Validation
Source of Truth: Frozen KAIZO Core + 36-Capability Audit + approved PHASE 2/3 decisions.
Validation Status: ARCHITECTURE VALIDATED; COMMERCIAL MARKET VALIDATION OPEN.
Open Unknowns: pricing, willingness-to-pay, acquisition channel, market size.
Open Conflicts: NONE CLOSURE-BLOCKING.
Core Change Required: NO.

## 9. Gate
GATE 4 = CLOSED.
Next approved phase: PHASE 5 — EPIC DESIGN.
