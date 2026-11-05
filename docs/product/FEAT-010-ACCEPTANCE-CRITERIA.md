# FEAT-010 — Coach Action History
Status: implementation acceptance contract for Draft PR #184.

## Dependencies
- FEAT-009 — read-only Coach decision-cycle workspace.
- FEAT-044 — decision-cycle state linkage.

## Scope
Provide a read-only, athlete-scoped timeline of actions attributable to the verified Coach, with related FEAT-044 decision-state links shown as lineage only when their decision and entity both resolve to the same owned athlete.

## Required behavior
- Verify athlete ownership using the authenticated Coach principal before reading history.
- Audit events are included only when both `tenant_id` and `who` match the verified tenant and Coach actor.
- Match audit events only through explicit top-level athlete identifiers or decision IDs belonging to that owned athlete.
- Never read unscoped legacy audit rows; never infer a tenant for them.
- FEAT-044 state links are included only when their decision record belongs to the owned athlete and `entity_id` equals that athlete ID.
- FEAT-044 `linked_by` is not verified identity; do not display or attribute it to the Coach. Mark its actor attribution as unverified.
- Do not expose raw old/new audit payloads, unrelated tenant events, or another Coach's actions.
- Missing durable audit, decision, ownership, or FEAT-044 link tables return `INSUFFICIENT_EVIDENCE`; no empty-history fallback.
- Memory adapter returns `INSUFFICIENT_EVIDENCE`; it does not fabricate action history.
- Reads do not append audit events, change state, or create historical backfills.

## Governance
- Coach Final Authority remains true.
- `execution_authorized=false`.
- No action replay, automatic approval, intervention, or state mutation.
- No changes to Frozen KAIZO Core or JCS.

## Acceptance
- API tests cover owner, anonymous/non-Coach denial, foreign Coach/tenant 404, and insufficient-evidence behavior.
- PostgreSQL integration proves tenant + Coach actor filtering, owned decision linkage, unscoped legacy exclusion, FEAT-044 entity/decision join, unverified actor labeling, and unchanged audit/link row counts.
- UI contract verifies the scoped endpoint, escaped display, explicit empty/insufficient states, and absence of write actions.
- Product runtime, identity, persistence, product contract, and FEAT-033–040 regression workflows pass.
- PR remains Draft and unmerged pending Coach review.
