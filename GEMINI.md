# KAIZO — Gemini Working Instructions

## Mandatory reading
Before changing code, read:
1. `docs/handover/KAIZO_V1.2_EXECUTION_AND_GEMINI_HANDOVER.md`
2. `docs/audits/KAIZO_STRATEGIC_AUDIT_20261011.md`
3. `docs/handover/GEMINI_MIGRATION_AND_SYNC_DESIGN_20261011.md`
4. `docs/product/KAIZO-MASTER-FEATURE-BACKLOG-V1-20261005.md`
5. Relevant feature, gate, and closure evidence for the task.

## Project invariants
- Evidence Before Claim.
- Reuse Before Rebuild; Verify Before Reuse.
- Better, not less; better every day, not more every day.
- Preserve coach final authority, human oversight, safety/HOLD behavior, auditability, and source provenance.
- Do not silently rewrite frozen baselines or delete historical evidence.
- Keep KAIZO methodology/decision engine distinct from JCS.
- Treat GitHub main as source of truth for merged code. Open PRs are proposals, not merged state.
- Do not invent names/statuses for the overall 17 Phases. Use only a verified canonical plan and evidence.

## Evidence rules
- Separate implemented, tested, integrated, runtime-verified, production-verified, and independently retested.
- CI success is not proof of live production health, real identity-provider connectivity, durable production persistence, or commercial activation.
- Every closure claim must cite the exact file, commit, workflow run, deployment, or runtime request that proves it.
- If evidence is inaccessible, state the limitation and do not claim completion.

## Change rules
- Prefer small, directly justified changes.
- Work on an isolated branch and open a PR; do not write directly to main.
- Run relevant tests and report exact results.
- Do not auto-merge or deploy to production.
- Never expose API keys, JWTs, database URLs, personal data, or other secrets.
- Ask for the smallest required human action when credentials, access, or approval is missing.
