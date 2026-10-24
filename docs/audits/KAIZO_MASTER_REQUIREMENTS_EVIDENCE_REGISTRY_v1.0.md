# KAIZO Master Requirements & Evidence Registry v1.0

**Status:** Initial controlled baseline — INVENTORY INCOMPLETE  
**Created:** 2026-10-24  
**Repository:** `hazemwahdan-spec/kaizo-system-`  
**Branch:** `audit/master-requirements-evidence-registry-2026-10-24`  
**Authority:** Proposed audit control artifact; not yet a replacement for any existing governed SSOT.

## Purpose

Create one auditable control surface that links each requirement to its origin, implementation location, acceptance criteria, verification method, evidence, blockers, and weighted completion contribution.

This v1.0 is an **initial controlled baseline**, not a claim that every KAIZO requirement has already been discovered. The full inventory must be reconciled against all source documents, features, epics, phases, issues, pull requests, workflows, code, runtime evidence, and the original KAIZO Library before an official whole-project percentage can be issued.

## Files

- `KAIZO_MASTER_REQUIREMENTS_EVIDENCE_REGISTRY_v1.0.csv` — one row per atomic requirement.
- `KAIZO_MASTER_EVIDENCE_LEDGER_v1.0.csv` — one row per evidence item; retain multiple items per requirement.
- `KAIZO_MASTER_REGISTRY_CONTROL_v1.0.json` — completeness and calculation guardrails.
- `KAIZO_MASTER_SCOPE_CROSSWALK_v1.0.csv` — 129-row index of strategic phases, board steps, product portfolio items, epics, and FEAT-001–075 IDs, with unresolved mappings preserved.
- `tools/kaizo_registry_completion.py` — deterministic CSV validation and calculation.

## Non-negotiable rules

1. **Evidence Before Claim:** a requirement is complete only when its predeclared acceptance criteria pass.
2. A file, code path, test definition, deployment event, or historical assertion is not by itself proof of a working production capability.
3. Evidence must identify the exact target environment, commit/build when available, observation time, outcome, and source URL or artifact.
4. Distinguish `VERIFIED_PASS`, `VERIFIED_FAIL`, `HOLD`, and `NOT_VERIFIED`. HTTP 503 is not an authorization PASS.
5. Keep historical evidence and current evidence separate. A historical PASS does not automatically establish current state.
6. A requirement can be closed only when acceptance criteria are satisfied, required evidence is verified, blockers are resolved, and closure is approved by an authorized reviewer.
7. `PARTIAL`, `OPEN_NOT_PROVEN`, `BLOCKED`, `NOT_VERIFIED`, and `FUTURE` earn zero completion credit by default. Do not award fractional credit unless an explicit, approved atomic sub-requirement is created.
8. Weights must be justified and frozen before official calculation. Do not change weights to improve the reported result.
9. Duplicate requirements must be linked, not silently deleted. Preserve all original source references.
10. Do not expose secrets, tokens, private user data, or sensitive production payloads in the registry.
11. Do not mutate production, close Issues/PRs, or merge changes as part of this audit.
12. Keep KAIZO and JCS distinct; preserve Coach Final Authority, Human Oversight, SSOT, and Safety/HOLD controls.

## Status vocabulary

- `CLOSED_VERIFIED` — all acceptance criteria passed with current, sufficient evidence and approved closure.
- `PARTIAL` — some implementation exists, but at least one acceptance criterion is unmet or unproven.
- `OPEN_NOT_PROVEN` — requirement remains open; evidence does not establish closure.
- `BLOCKED` — progress is prevented by a named dependency, decision, or external configuration.
- `NOT_VERIFIED` — insufficient current evidence to determine the actual state.
- `FUTURE` — approved target-scope capability not required for the declared baseline release.
- `DUPLICATE_LINKED` — retained source row linked to a canonical requirement; excluded from denominator only after approved deduplication.

## Evidence status vocabulary

- `VERIFIED_PASS`
- `VERIFIED_FAIL`
- `HOLD`
- `NOT_VERIFIED`
- `HISTORICAL_ONLY`

## Weighting policy

Weights represent relative requirement importance within a formally approved baseline. The initial seed weights are **provisional** and are for prioritization only. The official percentage remains suppressed until:
- requirement discovery is declared complete;
- the baseline scope is approved;
- duplicate and conflict reconciliation is complete;
- weights are reviewed and frozen;
- each requirement has acceptance criteria;
- the auditor approves the calculation baseline.

The calculation uses weighted binary completion: only `CLOSED_VERIFIED` rows with verified PASS evidence and closure approval earn credit. This avoids arbitrary partial percentages and prevents uncertain requirements from being counted as completed.

## Required audit trail

For each requirement, retain:
- immutable requirement ID;
- source reference(s);
- canonical requirement statement;
- scope and criticality;
- acceptance criteria and verification method;
- implementation references;
- evidence IDs;
- current status and status rationale;
- blocker and dependency links;
- weight and weight rationale;
- last verification time and verified commit/build;
- reviewer and closure approval details.

Evidence ledger entries must not overwrite each other. Add a new evidence row when a new run, deployment, test, or independent review occurs.

## Initial scope notes

The registry now contains 95 rows: 20 governance/project-control requirements plus 75 feature-level traceability requirements derived from the frozen master backlog. The scope crosswalk contains 129 entities: 5 strategic phases, 17 recovered board steps, 17 product portfolio items, 15 epics, and all 75 feature IDs with source-backed names, epics, priorities, horizons, and dependencies. Feature-level acceptance criteria, route/test evidence, current deployment proof, the original overall 17-phase plan, and source-library transfer reconciliation remain open. The PR #81 traceability map is a draft audit aid and its range-level coverage is not a feature-closure certificate.

## Official reporting gate

Until `inventory_complete` and `baseline_approved` are both `true` in the control file, the calculator must **not publish an official whole-project completion percentage**. It may report seed-row counts and the explicitly labeled seed-only ratio, but that ratio must never be described as project completion.

## Change control

Changes to this registry require:
1. a source reference or documented decision;
2. a reason for the change;
3. review of impact on scope, dependencies, weights, and prior calculations;
4. a new commit and retained history;
5. re-run of registry validation and calculation.

## Current known source references

- [README and audit boundary](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/README.md)
- [Master artifact inventory](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/docs/audits/master-artifact-inventory.md)
- [Complete library transfer status](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/docs/audits/complete-library-transfer-status.md)
- [Phase 4 security decision / evidence boundary, Issue #151](https://github.com/hazemwahdan-spec/kaizo-system-/issues/151)
- [Production target mismatch, Issue #154](https://github.com/hazemwahdan-spec/kaizo-system-/issues/154)
- [Phase 4 Auth0 academy tenant claims, PR #165](https://github.com/hazemwahdan-spec/kaizo-system-/pull/165)
- [Reject 503 as authorization proof, PR #164](https://github.com/hazemwahdan-spec/kaizo-system-/pull/164)
- [Phase 4 route authorization and remaining blockers, PR #128](https://github.com/hazemwahdan-spec/kaizo-system-/pull/128)

**Audit conclusion at creation:** this is a controlled initial registry seed. It is not yet the complete project baseline, and no official whole-project percentage is asserted.
