# FEAT-007 — Coach Today / Current-Priority Queue
Status: implementation acceptance contract for Draft PR #181.

## Scope
The Coach workspace may surface only review signals derived from persisted, tenant-owned workflow evidence. This queue is an orchestration/read surface; it does not own KAIZO Core intelligence or alter Core rules.

## Supported signals
1. An explicit FEAT-040 next-decision trigger with a non-empty trigger reason and required-evidence references.
2. A FEAT-036 training-response record with a session identifier and no FEAT-037 retest record for the same owned athlete and session.

## Required behavior
- Derive tenant and Coach actor only from the verified Coach principal.
- Restrict every record to athletes owned by that Coach in that tenant.
- Expose athlete, source feature, source record ID, recorded time, reason, and evidence references.
- Label every item as requiring Coach review; provide a suggested next step, not an instruction.
- Keep the queue read-only. No task, decision, retest, audit event, or workflow record is created by reading it.
- Keep Coach Final Authority true and execution_authorized false.
- Return insufficient_evidence when the adapter cannot verify the required persisted source records.
- Return no_current_items only when the source is available and no qualifying signals exist.

## Explicit non-goals
- No urgency score, numeric ranking, inferred deadline, due date, attendance, calendar, or synthetic task.
- No automatic closure, retest, decision, intervention, or state transition.
- No historical backfill and no changes to Frozen KAIZO Core or JCS.

## Acceptance
- Pure rules cover explicit triggers, unmatched response/retest pairs, missing evidence, and foreign athlete exclusion.
- PostgreSQL integration proves Coach/tenant isolation and read-only behavior.
- Anonymous and non-Coach requests are denied by the verified Coach API boundary.
- UI renders only returned evidence and fails closed on authorization or API errors.
- Workflow/contract tests pass; PR remains Draft and unmerged until reviewed.
