# FEAT-009 — Coach Decision-Cycle Workspace
Status: implementation acceptance contract for Draft PR #183.

## Dependencies
- FEAT-008 — verified athlete workflow navigation.
- FEAT-014 — assessment evidence attachment, DONE / VERIFIED.

## Scope
Provide a read-only, athlete-scoped workspace that assembles the existing persisted evidence and records across the decision cycle. The workspace is a review surface; it does not create a diagnosis, candidate, decision, intervention, training plan, retest, state snapshot, evidence attachment, or audit event.

## Data shown
For one athlete owned by the verified Coach in the verified tenant:
- Assessments and their recorded measurements.
- FEAT-014 assessment-evidence attachments and the linked evidence record metadata.
- Existing baseline/current-state snapshots.
- Existing problem statements, cause/context framings, and evidence-linked diagnoses.
- Existing decision candidates, rationales, comparisons, and Coach review records.
- Existing final decision records.
- Existing training plans, sessions, and FEAT-033–040 workflow records.
- Explicit source identifiers and recorded timestamps wherever the source record provides them.

## Required behavior
- Derive Coach and tenant identity only from the verified Coach principal.
- Verify athlete ownership before reading any workspace records; every database read is additionally filtered through the Coach/tenant ownership relation.
- Read evidence only through the assessment attachment relation; never expose unrelated global evidence records.
- Do not call the legacy unscoped `GET /api/v1/assessments/{id}/evidence` endpoint from the Coach UI.
- Return `INSUFFICIENT_EVIDENCE` if durable PostgreSQL sources or required tables are unavailable; do not silently treat missing storage as an empty cycle.
- If storage is available but no source records exist, return an explicit `NO_RECORDED_CYCLE` state.
- Preserve source lineage and show no fabricated links or missing values.
- All UI text from records is escaped; authorization/API errors fail closed.
- Workspace reads are read-only and do not append audit events or mutate any source table.

## Governance
- Coach Final Authority remains true.
- `execution_authorized=false`.
- No automatic decision, recommendation ranking, approval, intervention, or state transition.
- No historical backfill and no changes to Frozen KAIZO Core or JCS.
- Existing Core endpoints and FEAT-014 semantics remain unchanged.

## Acceptance
- API tests cover verified owner, anonymous/non-Coach denial, foreign Coach/tenant 404, insufficient-evidence behavior, and read-only behavior.
- PostgreSQL integration proves assessment/evidence linkage, complete cycle retrieval, Coach/tenant isolation, and unchanged audit/source row counts.
- UI contract verifies only the new scoped endpoint is used, every workspace section is rendered from returned source data, empty/insufficient states are explicit, and no mutation action is exposed.
- Product runtime, identity boundary, persistence, product contract where applicable, and FEAT-033–040 regression workflows pass.
- PR remains Draft and unmerged pending Coach review.
