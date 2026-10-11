# KAIZO Phase 4 Core API — Identity Boundary Route Inventory

**Inspection date:** 2026-10-11  
**Base commit inspected:** `391e76c283f02dfdf46c14e3863ec1d8f69bd67a`  
**Purpose:** Route mapping for P4-REQ-011 implementation; this is an inventory, not proof of enforcement.

## Primary decision-cycle routes in `backend/main.py`

| Route | Handler | Relevant actor/resource fields | Identity-boundary concern |
|---|---|---|---|
| `POST /api/v1/problem-statements` | `create_problem_statement` | athlete/resource reference; creator fields in request model | Establish resource ownership and tenant before creating the problem record. |
| `POST /api/v1/problem-statements/{problem_id}/diagnosis` | `create_evidence_linked_diagnosis` | `diagnosed_by`, `problem_id` | Caller-supplied actor string must not establish identity; verify actor role and access to the underlying athlete/problem. |
| `POST /api/v1/diagnoses/{diagnosis_id}/decision-candidates` | `generate_decision_candidates` | `requested_by`, `diagnosis_id` | Candidate generation must be authorized against the diagnosis/resource and verified evidence. |
| `POST /api/v1/decision-candidates/{candidate_id}/rationale` | `record_decision_rationale` | `created_by`, `candidate_id` | Enforce authenticated actor, resource scope and role. |
| `POST /api/v1/diagnoses/{diagnosis_id}/decision-comparisons` | `compare_decision_alternatives` | `diagnosis_id`; request actor | Same protected diagnosis scope and actor binding. |
| `POST /api/v1/decision-candidates/{candidate_id}/coach-review` | `coach_review_decision_candidate` | `coach_id`, `candidate_id`, coach action | Coach Final Authority must be an authenticated coach principal, not a body field alone. |
| `POST /api/v1/decision-candidates/{candidate_id}/decision-record` | `create_decision_record` | `candidate_id`, actor fields | Ensure the decision record links to an authorized, coach-reviewed candidate. |
| `POST /api/v1/training-plans` | `create_training_plan` | athlete/decision references, `created_by` | Plan remains a proposal; verify resource ownership and actor role. |
| `POST /api/v1/training-plans/{plan_id}/sessions` | `create_training_session` | `plan_id` | Inherit and verify the plan's athlete/tenant scope. |
| `POST /api/v1/training-sessions/{session_id}/dosage` | `create_training_dosage` | `session_id` | Inherit and verify session/plan/athlete scope. |
| `POST /api/v1/kpis/captures` | `capture_kpi` | athlete, KPI and actor fields | Enforce scope and role for athlete measurement. |
| `POST /api/v1/assessments` | `create_assessment` | `athlete_id`, `recorded_by` | Bind authenticated actor to assessment authority and athlete scope. |
| `POST /api/v1/assessments/{assessment_id}/evidence` | `attach_assessment_evidence` | `assessment_id`, evidence fields | Verify ownership/scope before attaching evidence. |
| `POST /api/v1/evidence` | `record_evidence` | `verified_by`, subject fields | A caller-provided verifier name is not identity proof. |
| `POST /api/v1/state-snapshots` | `create_state_snapshot` | athlete, assessment, KPI captures, `captured_by` | Check same-athlete linkage and authorization before capture. |
| `POST /api/v1/digital-twin/sync` | `synchronize_digital_twin` | `case_id`, `entity_id`, state | Validate caller authority and resource tenant before writing. |
| `POST /api/v1/decision/loop` | `decision_loop` | `case_id`, coach-authority boolean | Boolean is a workflow invariant, not authentication. |
| `POST /api/v1/decision/adapt` | `adapt_decision` | `case_id`, coach-authority boolean | Verify authenticated coach and scope; preserve Coach Final Authority. |

## Adjacent feature routers to include in the security review

- `backend/training_workflow.py`: `POST /feat-033/decision-drill` through `POST /feat-040/next-decision-trigger`, plus `GET /athletes/{athlete_id}`.
- `backend/knowledge_runtime.py`: FEAT-047 provenance, FEAT-048 lifecycle, FEAT-049 retrieval, FEAT-050 link.
- `backend/evidence_safety_runtime.py`: FEAT-057 evidence-quality, FEAT-058 provenance, FEAT-059 block, FEAT-060 escalate.
- `backend/state_cycle.py`: FEAT-042 digital-twin state, FEAT-043 state history, FEAT-044 decision-state link, FEAT-045 next-state.
- `backend/feature_runtime.py`: inspect router registration and all feature paths before defining the complete protected set; the route decorators are not all captured by a simple single-line decorator scan.

## Implementation rules

1. Treat this as a minimum primary-path inventory, not a complete endpoint list or passed security control.
2. Resolve the approved actor/role/tenant/consent contract from authoritative project artifacts before adding semantics. Do not infer consent from identity claims unless the approved contract says so.
3. Authenticate using the existing OIDC principal resolver; do not accept `X-KAIZO-Actor` or body actor fields as verified identity.
4. Authorize access against the underlying resource chain (decision/diagnosis → athlete; plan → athlete; session → plan; dosage → session; assessment/KPI/snapshot → same athlete) rather than trusting a caller-supplied tenant label.
5. Fail closed when enforcement is enabled and provider configuration/token validation is absent. Test all negative cases before any production activation.
6. Keep health/OpenAPI endpoints separately classified as public operational endpoints only if the approved security policy explicitly permits that classification.
7. Do not enable production enforcement until identity-provider configuration has been separately authorized and tested; do not run production writes before then.

## Current result

**P4-REQ-011: OPEN / NOT PROVEN.** This inventory is preparation for implementation and must not be used as evidence that any listed route is already protected.
