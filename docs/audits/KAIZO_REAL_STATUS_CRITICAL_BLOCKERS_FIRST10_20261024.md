# KAIZO — Real Status, Critical Blockers, First 10 Tasks & Closure Criteria

**Audit date:** 2026-10-24  
**Repository:** https://github.com/hazemwahdan-spec/kaizo-system-  
**Baseline branch:** `main`  
**Audit branch:** `audit/master-requirements-evidence-registry-2026-10-24`  
**Tracking PR:** [#166](https://github.com/hazemwahdan-spec/kaizo-system-/pull/166) — draft, not merged  
**Decision:** Phase 4 remains **OPEN / NOT PROVEN**. No official whole-project completion percentage is authorized.

## 1. Executive status — facts versus unknowns

| Area | Verified status | What this does not prove |
|---|---|---|
| Master feature inventory | The frozen product backlog on `main` contains FEAT-001–075 with names, epics, priorities, horizons and dependencies. | That every feature is accepted, deployed, usable by a real coach, or production-ready. |
| Requirements/evidence baseline | Draft PR #166 introduces a 95-row initial registry (20 governance/project controls + 75 feature rows), 14 evidence records, and a 129-entity scope crosswalk. | That this is the final denominator; the original overall 17-phase plan is still not recovered as one authoritative source. |
| Registry validator | GitHub Actions run [#40074772951](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/40074772951) completed successfully on PR #166's then-current head; the `validate-registry` job passed. | Runtime product correctness or Phase 4 closure. The run validates registry structure/calculation only. Re-check after any later commit. |
| Phase 4 code | Relevant implementation and workflow candidates exist, including merged PR #162 for tenant-scoped audit reads and the live academy-isolation workflow on `main`. | That the currently deployed service enforces the complete policy. Code presence and unit/CI success are not production proof. |
| Anonymous denial / containment | Historical live run [#39148814079](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39148814079) passed its workflow steps while observing HTTP 503 on anonymous protected reads. | 503 is containment/HOLD, not proof of intended 401/403 authorization. PR #164 explicitly corrects this distinction and remains open. |
| Production target | Issue [#154](https://github.com/hazemwahdan-spec/kaizo-system-/issues/154) records a target mismatch: the commercial workflow hardcodes FastAPI Cloud while the cited containment deployment is on Railway. | That either URL is the sole canonical production target today. Current live health endpoints could not be independently queried through this audit interface. |
| Tenant isolation | Workflow [phase4-live-academy-tenant-isolation.yml](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/.github/workflows/phase4-live-academy-tenant-isolation.yml) exists and requires two distinct academy clients, signed tenant claims, persisted records, and spoofing resistance. | That the external Auth0 setup/secrets are present or that the live workflow currently passes. Those facts are not established by source inspection. |
| Consent and durable audit | Open security gate [#151](https://github.com/hazemwahdan-spec/kaizo-system-/issues/151) lists remaining consent, route-policy, persistence and independent-retest requirements. | Guardian approval/revocation behavior or complete durable audit guarantees in current production. |
| Commercial readiness | The repository has product-surface/runtime workflows and a 75-feature backlog. | That a controlled pilot or commercial launch is approved. |

**Reporting rule:** No official project-wide percentage until scope is reconciled, duplicates/conflicts resolved, weights approved, and independent baseline approval recorded. All feature-level rows remain partial until each has its own acceptance evidence.

## 2. Critical blockers (ordered by dependency)

1. **Production identity is ambiguous.** FastAPI Cloud and Railway evidence are mixed across workflows/issues; evidence can be attributed to the wrong host/build.
2. **Deployed build identity is not sufficiently tied to test results.** A passing workflow commit is not automatically the commit running in production.
3. **Authorization denial evidence has been overstated historically.** HTTP 503 means HOLD/containment, not a valid 401/403 authorization decision.
4. **Auth0 tenant identities are not proven live.** The isolation workflow needs two distinct M2M clients and trusted, signed, distinct tenant claims.
5. **Cross-tenant isolation is not proven end-to-end.** It requires non-empty persisted records for both tenants, own-tenant allow, cross-tenant deny, and tenant-spoof resistance.
6. **Route-level policy reconciliation is incomplete.** The actual route table must be reconciled against explicit authentication, role, tenant, parent-resource, consent and audit requirements; a generic fail-closed backstop is insufficient.
7. **Guardian consent lifecycle is not proven in production.** Trusted guardian relationship, approve, revoke, expired/missing consent, and denied writes need positive and negative tests.
8. **Durable audit guarantees are incomplete as production evidence.** Prove tenant-scoped reads, atomic persistence, immutable linkage/IDs, and safe behavior when the audit store is unavailable.
9. **Global evidence publisher policy remains gated.** Safe write denial and publisher/non-publisher/wrong-tenant/forged-token behavior must be tested before any enablement.
10. **The master baseline is still initial.** The original 17-phase plan and full project scope must be reconciled with the recovered 17-step board, five strategic phases, P01–P17 portfolio, epics and 75 features—without treating them as interchangeable counts.

## 3. First 10 tasks — execution order and closure tests

### T01 — Freeze the canonical production target map
**Owner:** Release/Platform + Security  
**Actions:** Record each intended production surface separately (Core API, coach UI, any supporting API); identify the authoritative URL for each; update workflow configuration only after the target is explicitly approved. Keep evidence for different hosts separate.  
**Close only when:** An approved target map names host, service, environment, owner and intended use; relevant workflows print the target host; no workflow silently attributes evidence to another host. Link: [Issue #154](https://github.com/hazemwahdan-spec/kaizo-system-/issues/154).

### T02 — Bind each runtime result to the exact deployed build
**Owner:** Platform/SRE  
**Actions:** Expose or otherwise independently verify a safe build/commit identifier for each canonical service; record deployment ID, deployed SHA, environment, observation time and test run.  
**Close only when:** A fresh runtime probe proves the exact deployed SHA is the intended candidate or its approved descendant; workflow commit and deployed runtime SHA are recorded separately; independent reviewer confirms the relationship.

### T03 — Correct the authorization-denial acceptance gate
**Owner:** Security + QA  
**Actions:** Complete review of [PR #164](https://github.com/hazemwahdan-spec/kaizo-system-/pull/164); keep 503 as HOLD, and only accept expected 401/403 for the relevant anonymous/invalid-credential cases. Do not merge until required checks on the current head pass.  
**Close only when:** Current-head CI passes; live anonymous and invalid-token probes return the expected 401/403 on protected routes; health remains available; 503, 404, timeout and 5xx are explicitly classified as non-PASS.

### T04 — Complete trusted Auth0 setup for two academy tenants
**Owner:** Identity/Security  
**Actions:** Review [PR #165](https://github.com/hazemwahdan-spec/kaizo-system-/pull/165); configure and attach the claims Action; create two separate Academy A/B M2M clients with trusted distinct tenant metadata; verify the five workflow secrets exist without printing values.  
**Close only when:** Workflow obtains short-lived tokens for both clients; API-audience tokens have verified signatures/issuer/audience/expiry and distinct trusted academy role/tenant claims; missing or untrusted metadata fails closed. Configuration presence alone is not closure.

### T05 — Prove live cross-tenant isolation with persisted data
**Owner:** Security + Backend + QA  
**Actions:** Run [the live academy tenant-isolation workflow](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/.github/workflows/phase4-live-academy-tenant-isolation.yml) against the T01-approved host after T02 is satisfied.  
**Close only when:** Both tenants have non-empty persisted records; each tenant can read only its own records; cross-tenant access is denied; spoofing `tenant_id` in a request cannot alter scope or result set; workflow run, deployed SHA and redacted evidence are retained. Empty data or HTTP 503 = HOLD, not PASS.

### T06 — Reconcile every protected route to an explicit policy
**Owner:** Backend Security + Architecture  
**Actions:** Generate the actual mounted-route inventory and map each route to authentication, allowed roles, tenant derivation, parent ownership, consent requirement, audit behavior, and expected denial response. Resolve uncovered routes and conflicts.  
**Close only when:** 100% of in-scope routes map to an approved policy; automated test proves no unmapped protected route is exposed; positive and negative route tests pass; independent review signs the route-policy manifest. No percentage credit from range-level mappings.

### T07 — Prove guardian consent lifecycle end-to-end
**Owner:** Backend + Product/Safeguarding + QA  
**Actions:** Verify trusted guardian-to-athlete relationship; test approval, revocation, missing consent, expired consent, wrong guardian, wrong tenant and attempted writes after revocation.  
**Close only when:** Production-backed tests show approved consent permits only the explicitly allowed action; revoked/missing/expired/wrong-scope consent denies access; changes persist durably and create traceable audit events; no test relies only on mocks or seeded in-memory state.

### T08 — Prove durable, tenant-scoped audit behavior
**Owner:** Data + Backend + SRE  
**Actions:** Verify transaction boundaries for protected mutation plus audit event, tenant-scoped reads, immutable event linkage/IDs, and database-unavailable behavior. Preserve the rule that legacy NULL-tenant rows are not retroactively attributed.  
**Close only when:** A production-like or approved production acceptance run demonstrates persistence across restart, correct tenant scope, atomic success/failure behavior, and fail-closed handling when storage is unavailable; independent reviewer verifies records without exposing sensitive data.

### T09 — Close the global evidence-publisher security decision
**Owner:** Security + Product Governance  
**Actions:** Keep publishing disabled while the policy is unresolved; test safe write denial without risking a production mutation, then verify publisher allow, non-publisher deny, wrong-global-tenant deny, forged verifier rejection, immutable IDs and durable atomic audit.  
**Close only when:** Explicit policy decision is recorded; all positive/negative tests pass against the approved build; rollback/disable path is demonstrated; only the authorized approver can authorize enablement. Do not enable as a shortcut to passing tests.

### T10 — Independent Phase 4 red-team, release decision and freeze
**Owner:** Independent Security Reviewer + Release Owner  
**Actions:** Run the complete current-head CI suite, production smoke, same-/cross-tenant matrix, consent lifecycle, audit persistence/failure tests and regression/rollback checks. Reconcile evidence ledger and closure records.  
**Close only when:** Every required gate has current reproducible PASS evidence tied to host + deployed SHA + run + timestamp; no unresolved critical/high security finding remains; independent reviewer signs the evidence; release owner records the decision. Until then: **Phase 4 OPEN / NOT PROVEN; commercial publishing disabled.**

## 4. Evidence record required for every task

Every task must record: requirement/task ID; owner; acceptance criteria; source decision; code commit; CI/workflow run; environment and canonical host; deployed SHA/deployment ID; observed time; redacted proof URL/artifact; result (PASS/FAIL/HOLD/NOT VERIFIED); reviewer; closure approver and date.

- **PASS:** All acceptance criteria met with current evidence.
- **FAIL:** A criterion was tested and failed.
- **HOLD:** Blocked, unavailable, ambiguous, or returned 503/timeout/empty data where proof is required.
- **NOT VERIFIED:** No adequate current evidence was collected.
- Historical documentation, mocks, simulations, static code presence and range-level matrices never count as current production PASS.

## 5. Baseline and sequencing decisions

- Keep V1.0 frozen; continue V1.1 through its controlled execution path [Issue #74](https://github.com/hazemwahdan-spec/kaizo-system-/issues/74).
- Keep [PR #166](https://github.com/hazemwahdan-spec/kaizo-system-/pull/166) as a draft until its baseline is reviewed; do not merge it as if it closes runtime blockers.
- The original overall 17-phase plan remains unrecovered as a single authoritative source; do not claim 7/17 or another whole-project percentage from mismatched taxonomies.
- After T01–T10, proceed feature-by-feature from the frozen FEAT-001–075 backlog in dependency order, with a unique acceptance test and evidence row per feature. No batch closure from shared/range-level evidence alone.
- No production secrets, user data, or security gates are changed by this audit document.

## 6. Approval requested

Approve or amend the following four decisions before the execution plan expands:
1. The canonical host/service map (T01).
2. The acceptance standard that 503/404/timeout/empty data are never authorization PASS.
3. The T01–T10 order and their evidence-based closure gates.
4. The rule that no official completion percentage or Phase 4 closure is published before independent verification.
