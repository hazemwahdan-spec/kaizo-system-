# KAIZO T01 — Canonical Production Target Map

**Audit date:** 2026-10-24  
**Task:** T01 — Freeze the canonical production target map  
**Status:** **PARTIAL / DECISION REQUIRED**  
**Approved execution order:** T01 → T10 (user approved in chat on 2026-10-24)  
**Security boundary:** No production URL, secret, or deployment configuration was changed by this task.

## 1. Decision principle

KAIZO does not currently have one safely assumable universal production URL. The repository contains distinct deployments and workflows that use different hosts. Treat each host as service-specific; do not copy a PASS from one host to another. A target becomes canonical only after the service owner confirms its intended role and current runtime/build identity is independently verified.

## 2. Source-backed target inventory

| Surface / evidence purpose | URL currently documented in source | Source evidence | Current audit classification |
|---|---|---|---|
| Coach UI / commercial product surface | `https://kaizo-coach-production.up.railway.app` | [P01 Coach UI closure record](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/docs/audits/P01-COACH-UI-CLOSURE-20260930.md) records a Railway service/deployment and the coach domain. | **Documented target; current live state and deployed SHA must be reverified.** |
| KAIZO Core Engine API | `https://kaizo-core-engine-production.up.railway.app` (API base: `/api/v1`) | [Frontend README](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/frontend/README.md) identifies this as the runtime API. [Issue #154](https://github.com/hazemwahdan-spec/kaizo-system-/issues/154) records a Railway containment deployment and health HTTP 200 as of 2026-10-19. | **Documented Core API target; historical health/deployment evidence is not a current live proof.** |
| V1.1 commercial OIDC / authorization evidence workflow target | `https://kaizo-system.fastapicloud.dev` | [V1.1 commercial workflow](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/.github/workflows/v1-1-commercial-production-evidence.yml) hardcodes this URL and prints `TARGET_HOST`. [Phase 4 runtime smoke workflow](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/.github/workflows/phase4-live-runtime-smoke.yml) also targets FastAPI Cloud. | **Workflow-specific target; do not attribute its results to Railway. Confirm whether this is a distinct production API surface or a second deployment of overlapping functionality.** |
| Phase 4 academy tenant isolation workflow | Defaults to `https://kaizo-system.fastapicloud.dev`; can be overridden with `KAIZO_PHASE4_PRODUCTION_BASE_URL`. | [Academy isolation workflow](https://github.com/hazemwahdan-spec/kaizo-system-/blob/main/.github/workflows/phase4-live-academy-tenant-isolation.yml). | **Target is configurable but not approved by configuration alone. Must be explicitly assigned to the service where the tested isolation routes are deployed.** |

## 3. Confirmed mismatch and required resolution

[Issue #154](https://github.com/hazemwahdan-spec/kaizo-system-/issues/154) explicitly records that the V1.1 commercial workflow targets FastAPI Cloud while the cited Phase 4 containment deployment was on Railway Core Engine. The issue says the workflow does not, by itself, prove the Railway containment behavior.

The correct response is **not** to globally replace every URL with one host. Instead:
1. Keep Coach UI and Core Engine API as separately identified Railway services.
2. Keep FastAPI Cloud as the target of the V1.1 commercial workflow unless the service owner formally changes that workflow's purpose.
3. Assign each Phase 4 test to the actual service that hosts its tested routes. Record the resolved target as a workflow input and print it in every run.
4. Do not merge/close Phase 4 based on a passing check against a different host.

## 4. T01 closure criteria

T01 is **not closed yet**. Close only when all conditions are met:

- [ ] Service owner explicitly confirms the role of each listed host: Coach UI, Core Engine API, and FastAPI Cloud commercial OIDC/evidence target.
- [ ] The Phase 4 academy-isolation workflow target is explicitly assigned to the correct service; its run prints the resolved target host.
- [ ] Fresh health probes confirm the intended service is reachable on its approved host.
- [ ] Each service's currently deployed commit/build identity is recorded or independently verified; a historical deployment record is not enough.
- [ ] The target map is linked from the evidence ledger and approved by the release owner.
- [ ] No workflow result is used as proof for another host or service.

Until these checks are met, classify T01 as **PARTIAL / DECISION REQUIRED**, not PASS.

## 5. Next execution step after target approval

Once the host/service roles are approved, perform T02: tie the exact deployed build SHA/deployment ID to each target, then run the appropriate live tests. T03's authorization-denial gate must keep HTTP 503/404/timeouts and other unexpected 5xx responses classified as HOLD/non-PASS.

## 6. User-approved governance

The user approved the T01–T10 sequence and evidence-based closure criteria on 2026-10-24. This does not automatically approve any specific production URL or alter the production target configuration.
