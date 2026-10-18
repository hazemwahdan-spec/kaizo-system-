# KAIZO Phase 4 — Route/Resource Scope Coverage Audit

Date: 2026-10-13  
PR: [#128 — Phase 4 Core resource authorization](https://github.com/hazemwahdan-spec/kaizo-system-/pull/128)  
Validated candidate branch: `feat/phase4-core-resource-authorization`  
Disposition: **BLOCKED — CI is green, production security proof remains incomplete**

## Latest checkpoint — 2026-10-13

The following runs were directly inspected and completed successfully:

- [Persistence Adapter Validation run 38427546736](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38427546736): PASS. Step 40, “Run Phase 4 actual Core resource authorization HTTP acceptance tests,” completed successfully alongside the persistence and feature acceptance suite.
- [Phase 4 Actual Core Route Inventory run 38427546657](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38427546657): PASS. This proves the route-inventory assertions and configured identity/scope guard wiring for the candidate tested by that run.
- [Phase 4 Live Runtime Smoke run 38427546821](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38427546821): PASS for deployed OpenAPI and `GET /api/v1/health` only.

**Evidence boundary:** the live smoke does not verify production OIDC issuer/audience/JWKS/claim mapping, does not prove that the candidate branch is deployed, and does not exercise live positive/negative tenant and guardian-consent authorization. CI acceptance tests are candidate-code evidence and are not equivalent to an independent production security retest.

## Newly identified execution blocker — commercial evidence workflow

The existing `.github/workflows/v1-1-commercial-production-evidence.yml` targets `https://kaizo-core-engine-production.up.railway.app` and uses Auth0 client-credentials secrets `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, and `AUTH0_CLIENT_SECRET`, with audience `https://api.kaizo.system`. The separately documented current FastAPI Cloud deployment is `https://kaizo-system.fastapicloud.dev`. These are distinct deployment targets.

The workflow was inspected in source, but no workflow-dispatch capability is available in this execution context, and no run was initiated. Do not claim that live OIDC verification ran. Before dispatch, an operator must confirm which host is the intended production target, that the Auth0 audience and client are configured for that target, and that the live `/api/v1/product/auth/oidc/verify` route is present there. Do not paste credentials or bearer tokens into chat. A green result against the wrong host would not close the gate.

## Existing route/resource findings

The source-derived route manifest is [KAIZO_PHASE4_ROUTE_RESOURCE_AUTHORIZATION_MANIFEST_20261013.md](https://github.com/hazemwahdan-spec/kaizo-system-/blob/feat/phase4-core-resource-authorization/docs/audits/KAIZO_PHASE4_ROUTE_RESOURCE_AUTHORIZATION_MANIFEST_20261013.md). It records 99 statically declared decorator routes across ten backend files and separately lists three dynamically generated feature-route patterns. It is an audit baseline, not proof that every runtime route has a complete authorization contract.

The candidate includes tenant-bound parent-chain checks and guardian-consent checks for covered Core athlete/assessment resources, durable authorization audit behavior, fail-closed handling for unsupported scope mappings, and a shared backstop for mounted/generated routers. The shared backstop is not a substitute for explicit route-by-route resource, parent, role, consent, and audit policies.

## Remaining closure gates

1. Complete explicit per-route policy mapping and reconcile the manifest against the actual registered/deployed route table.
2. Complete route-by-route wrong-parent and cross-tenant no-read/no-write tests, missing/revoked/expired consent tests, and durable-audit verification.
3. Establish a trusted operational process for age classification and guardian-relationship verification; database records alone do not prove attestation trust.
4. Implement persisted tenant/subject/actor ownership for generated feature records before enabling those routes for production principals.
5. Define explicit global-versus-academy ownership and role policies for shared catalogs and knowledge ingestion/publication.
6. Independently verify production OIDC issuer, audience, JWKS, token claims, canonical migrations, and live allow/deny behavior against the exact deployed candidate.
7. Resolve the workflow target/audience configuration, execute live positive/negative authorization tests against the exact intended deployment, and capture independent retest, rollback/regression, and deployment evidence.

## Governance decision

- `P4-REQ-011 = OPEN / NOT PROVEN`
- `Phase 4 EXIT = BLOCKED`
- PR #128 remains draft/open/unmerged.
- No production settings were changed and no live identity/authorization activation claim is made.

**Evidence Before Claim.** Do not merge PR #128 or close Phase 4 based on green CI and health/OpenAPI smoke alone.

## Follow-up code inspection — OIDC endpoint proof boundary

The candidate implementation at [productization/product_api.py](https://github.com/hazemwahdan-spec/kaizo-system-/blob/feat/phase4-core-resource-authorization/productization/product_api.py) mounts `GET /api/v1/product/auth/oidc/verify` and delegates to `verify_bearer_token`. [productization/identity.py](https://github.com/hazemwahdan-spec/kaizo-system-/blob/feat/phase4-core-resource-authorization/productization/identity.py) requires runtime configuration `KAIZO_OIDC_ISSUER`, `KAIZO_OIDC_AUDIENCE`, and `KAIZO_OIDC_JWKS_URL`; missing configuration causes the route to return HTTP 401. It validates RS256 signature, issuer, audience, and required `sub`/`iss`/`aud`/`exp` claims.

**Important limitation:** this verification endpoint returns `verified=true` and `source=oidc_jwt` after standard JWT verification, but it does not itself prove KAIZO role/tenant membership, resource ownership, or guardian consent. The separate `resolve_bearer_principal` path additionally requires a valid KAIZO role and tenant claim; live authorization tests must exercise protected resource endpoints and demonstrate both allowed and denied outcomes. An Auth0 token-issuance success alone is not sufficient.

The workflow's fixed Auth0 audience (`https://api.kaizo.system`) must exactly match the deployed service's `KAIZO_OIDC_AUDIENCE`; the issuer must match the Auth0 tenant issuer and JWKS URL must point to that same issuer's JWKS. These values should be checked as presence/consistency without printing secrets. Until host and runtime configuration are confirmed, no production verification run should be inferred from source inspection.


## Production-evidence workflow correction and execution checkpoint — 2026-10-13

The candidate branch workflow `.github/workflows/v1-1-commercial-production-evidence.yml` was re-read at blob `c9208eeb4705f00c134fe9aeca6678312e2ef11b`. It targets the canonical FastAPI Cloud host `https://kaizo-system.fastapicloud.dev`, requests a short-lived Auth0 client-credentials token using GitHub Actions secrets, masks the token, and checks the live OIDC verification endpoint plus `/api/v1/health`. The workflow explicitly states that these checks do **not** prove route-level RBAC, tenant isolation, guardian consent, durable audit, or full commercial activation.

Execution evidence was rechecked:
- [Phase 4 Live Runtime Smoke run 38432291475](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38432291475): job succeeded; its only substantive checks were deployed OpenAPI contract and health endpoint. It is **not** an execution of the corrected commercial OIDC workflow.
- [Persistence Adapter Validation run 38432291418](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38432291418): job succeeded; step 40, actual Core resource authorization HTTP acceptance tests, completed successfully. This remains candidate-code CI evidence, not independent live-production allow/deny evidence.

The corrected workflow has been inspected in the candidate branch, but no dispatch/run result is available in this execution context. Therefore the audit records no claim that Auth0 token issuance, live OIDC verification, or live resource authorization has passed. Before closure, execute the workflow from the candidate branch and then independently exercise protected production routes with both allowed and denied cases (including cross-tenant access and missing/revoked guardian consent), reconcile runtime route coverage, and capture independent retest plus rollback/regression evidence.

Governance remains unchanged: `P4-REQ-011 = OPEN / NOT PROVEN`; `Phase 4 EXIT = BLOCKED`; PR #128 remains draft/open/unmerged. Evidence Before Claim.


## Resume checkpoint — 2026-10-18

This checkpoint records a fresh source inspection only; it does not claim a new workflow execution or live security pass.

- Commercial evidence workflow blob inspected: `203104101d54336a99471a81d6f836d0f48362f1`.
- Configured target in that file: `https://kaizo-system.fastapicloud.dev`.
- Workflow steps present in source: Auth0 client-credentials token request (masked), positive OIDC verification, invalid-bearer rejection expecting HTTP 401, and production health verification.
- Actual-app route inventory test blob inspected: `d2fdd4059ed9546b57049c38cc123831d4a2b3ce`. It checks that registered Core API routes are represented in the manifest and that the shared identity/scope guards are wired.
- The same test explicitly documents that the generic mounted-route guard is not a substitute for route-specific ownership, role, consent, and audit policies.

### Closure decision

No fresh dispatch result was available from this inspection. Source presence is not execution evidence. No claim is made that the live OIDC workflow passed on 2026-10-18, that the candidate branch is deployed, or that live protected-resource allow/deny cases passed.

Remain blocked until an operator confirms the intended deployment and Auth0 audience/configuration, runs the workflow, and obtains independent live positive/negative resource-authorization evidence. The route-by-route policy, trusted guardian verification, generated-feature ownership, shared catalog policy, durable-audit proof, and independent retest/rollback evidence remain open.

- `P4-REQ-011 = OPEN / NOT PROVEN`
- `Phase 4 EXIT = BLOCKED`
- PR #128 remains draft/open/unmerged.

**Evidence Before Claim.**

## Cross-PR regression check — 2026-10-18

A separate, narrow follow-up PR was inspected: [#148 — forward verified identity context for parent progress](https://github.com/hazemwahdan-spec/kaizo-system-/pull/148), head `c766844bb7219719fabc04e3b4e9eb6cf5bc6113`, based on `main` at `cf4a895885b836b56540bf113f7b8074af0f4769`.

- The patch forwards the incoming Authorization header to the parent-progress identity context.
- It adds a focused regression test asserting the header reaches that context.
- The following candidate-code CI runs were retrieved and their jobs reported success:
  - [Commercial Security Regression run 39073541978](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39073541978)
  - [Identity RBAC Boundary run 39073541975](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39073541975)
  - [Persistence Adapter Validation run 39073541995](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39073541995)
- PR #148 is still draft/open/unmerged. Its test isolates route wiring; it is not a live Auth0, tenant-isolation, guardian-consent, or deployed-production authorization test.
- This PR is based on `main`, not the Phase 4 candidate branch. Its green runs must not be attributed to PR #128 or treated as Phase 4 exit evidence.

Decision remains unchanged: `P4-REQ-011 = OPEN / NOT PROVEN`; `Phase 4 EXIT = BLOCKED`. Do not merge or close based solely on these checks.


## Follow-up triage — overlapping identity fix and Auth0 scope — 2026-10-18

### Parent-progress Authorization forwarding

Two open requests contain the same one-line production-route change and essentially the same focused regression assertion:

- [PR #133](https://github.com/hazemwahdan-spec/kaizo-system-/pull/133), head `a3f57ea932661e7587c27e88c4f80cd5aeb2d1f8`, currently open and non-draft.
- [PR #148](https://github.com/hazemwahdan-spec/kaizo-system-/pull/148), head `c766844bb7219719fabc04e3b4e9eb6cf5bc6113`, currently open and draft.

Both PR patches change `productization/product_api.py` to pass the Authorization header to `ctx(...)`. Both include a regression test for header forwarding. CI runs retrieved for PR #133's head and PR #148's head reported success for their respective listed workflows. These are separate candidate branches; the same change must not be merged twice or their test results combined as if one candidate had all coverage. A maintainer should select a canonical PR after reviewing the complete diff and base/branch freshness, then close or supersede the duplicate only after the chosen change is integrated and verified. No merge was performed.

### Auth0 product API scope request

[PR #147](https://github.com/hazemwahdan-spec/kaizo-system-/pull/147), head `dfd668739bfd27a011ad875319154dc9420a3aa5`, requests the `product` scope in Auth0 SPA initialization, redirect login, and silent token acquisition. The retrieved candidate-code runs listed for this head reported success, including [Persistence Adapter Validation run 39029745998](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39029745998) and [Identity RBAC Boundary run 39029746010](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39029746010). PR #147 remains draft/open/unmerged. CI cannot grant the permission in the Auth0 dashboard or prove that the configured API audience/scope is accepted by the live provider. Provider-side permission and live token claims remain unverified.

### Gate disposition

These findings improve review clarity but do not satisfy the Phase 4 production authorization exit criteria. Keep `P4-REQ-011 = OPEN / NOT PROVEN` and `Phase 4 EXIT = BLOCKED`. No production configuration, secrets, or live data were changed.


## Next-step checkpoint — PR state and CI refresh — 2026-10-18

Fresh PR metadata and workflow-run associations were retrieved:

- **PR #128** remains open/draft; its current head is this audit checkpoint commit `618ed37631c22282001bbe9faad5c5b713cc4f65`. The PR is not mergeable according to current GitHub metadata. No merge or activation was attempted.
- **PR #148** remains open/draft at `c766844bb7219719fabc04e3b4e9eb6cf5bc6113`. Ten associated candidate-code workflows returned `success`, including [Commercial Security Regression](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39073541978), [Identity RBAC Boundary](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39073541975), and [Persistence Adapter Validation](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/39073541995). This is green CI for PR #148's own candidate head only.
- **PR #133** remains open/non-draft at `a3f57ea932661e7587c27e88c4f80cd5aeb2d1f8`; the retrieved associated workflows were successful, but the PR is reported not mergeable. Its wider patch is not interchangeable with the narrow PR #148 change. Do not treat the two branches' green checks as one candidate's evidence.
- **PR #147** remains draft/open at `dfd668739bfd27a011ad875319154dc9420a3aa5`; its retrieved workflows are green, but the Auth0 dashboard permission grant and live access-token scope/audience are not verified.

### Immediate sequencing decision

1. Resolve the mergeability/conflict state of the Phase 4 PR #128 and refresh its CI on the final candidate head.
2. Review the complete diffs and branch ancestry of PR #133 and #148; choose a canonical route-forwarding fix only after confirming whether PR #133's broader changes are required. Avoid double-merging.
3. Keep PR #147 draft until frontend tests and provider-side scope/audience validation are available.
4. Dispatch the commercial production evidence workflow and perform independent live positive/negative authorization tests only when an authorized maintainer can run it and production identity secrets/configuration are available.

No fresh workflow dispatch, production request, Auth0 dashboard mutation, secret change, or merge was performed in this checkpoint. `P4-REQ-011 = OPEN / NOT PROVEN`; `Phase 4 EXIT = BLOCKED`.

## Branch divergence and evidence refresh — 2026-10-18

### PR #128 ancestry / CI refresh

A fresh compare of `main` against `feat/phase4-core-resource-authorization` returned `status=diverged`, `ahead_by=255`, `behind_by=54`, with merge base `cd42f2f6503812434fb06ef96746444718f90dd6` and current `main` base commit `cf4a895885b836b56540bf113f7b8074af0f4769`. PR #128 remains open/draft and GitHub reports `mergeable=false`. This confirms substantial branch divergence, but the connector response does not expose a definitive file-by-file conflict list. Do not attempt a blind merge, rebase, or force-update; resolve conflicts against the current base and rerun the required checks on the final candidate head.

The audit file exists on the Phase 4 branch but was not found on `main` at the same path. A workflow-run lookup for audit commit `618ed37631c22282001bbe9faad5c5b713cc4f65` returned no PR-triggered workflow runs, and combined commit status returned no statuses. Therefore this documentation commit has no fresh CI evidence from those endpoints; it must not be represented as a code-validation run.

### Separate candidate fixes / remaining live proof

- PR #148 is open/draft and mergeable according to GitHub metadata; its focused patch forwards the Authorization header to `ctx(...)` and asserts forwarding. Its green candidate workflows are not evidence for PR #128 or #133.
- PR #133 is open/non-draft but reported not mergeable. Its patch is broader and includes fail-closed audit endpoint expectations; review the complete diff before selecting it over #148. Do not integrate both copies of the same forwarding fix.
- PR #147 remains open/draft. Its frontend scope request has green candidate-code checks, but Auth0 API permission configuration and a live token's audience/scope remain unverified.
- The commercial production evidence workflow has not been freshly dispatched in this checkpoint. No production request, Auth0 change, secret mutation, or merge was performed.

### Current gate

`P4-REQ-011 = OPEN / NOT PROVEN`; `Phase 4 EXIT = BLOCKED`. Remaining proof includes route-level identity/role/tenant/ownership enforcement, guardian relationship and active consent, durable audit, independent live positive and negative authorization tests, and fresh CI on the final integrated candidate.
