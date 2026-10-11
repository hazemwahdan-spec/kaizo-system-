# KAIZO — Gemini Migration and Update Synchronization Design

**Date:** 2026-10-11  
**Status:** Proposed contract; automatic sync is NOT yet verified  
**Code source of truth:** `hazemwahdan-spec/kaizo-system-`

## 1. Objective

Let Gemini work against current KAIZO repository context without losing decisions. Separate:
1. Repository context access.
2. AI-assisted change/review automation.
3. Gemini Apps repository attachment, which is a snapshot rather than a live synchronized working copy.

Google's current Gemini Apps help explicitly states repository changes are not synced after import and repository attachment is currently unavailable on mobile. Do not promise automatic updates inside an already imported Gemini Apps snapshot.

## 2. Recommended architecture

Use GitHub as source of truth for merged code and versioned context. Use Gemini CLI via GitHub Actions for event-triggered analysis and PR-based changes.

```text
GitHub main / Pull Request
        |
        v
CI checks + policy gates
        |
        +--> Validate versioned project context
        |
        +--> Gemini CLI GitHub Action (review / requested task)
        |
        v
Proposed branch / Pull Request
        |
        v
Tests + human review + approval
        |
        v
Merge to main
```

Gemini is a collaborator, not the source of truth. No autonomous production deployment is authorized.

## 3. Existing context to reuse

- `docs/handover/KAIZO_V1.2_EXECUTION_AND_GEMINI_HANDOVER.md`
- `docs/product/KAIZO-MASTER-FEATURE-BACKLOG-V1-20261005.md`
- `docs/product/KAIZO-PRODUCTIZATION-PHASE-7-RELEASE-PLAN-20261005.md`
- `docs/audits/KAIZO_STRATEGIC_AUDIT_20261011.md`
- Current closure evidence and the approved overall 17-Phase plan, once located.

Do not create duplicate master plans. The canonical overall 17-Phase plan remains unverified; Gemini must not invent phase names or statuses.

## 4. Project-level Gemini instructions

A root `GEMINI.md` should require Gemini to:
- read project instructions and current state before coding;
- preserve frozen baselines and historical records;
- reuse before rebuild and avoid scope expansion;
- never claim CI success as production verification;
- report exact commit, run, and evidence links;
- avoid secrets and production personal data;
- require human approval for deployment, destructive changes, governance decisions, and security-sensitive changes;
- stop and request the smallest human action if required secrets or permissions are missing.

## 5. Automation option — Gemini CLI GitHub Action

The official `google-github-actions/run-gemini-cli` supports event-driven workflows, PR review, issue triage, on-demand collaboration, and project instructions in `GEMINI.md`. For Google AI Studio API-key authentication, it commonly uses a GitHub Actions secret named `GEMINI_API_KEY`. Store it only in GitHub Actions Secrets, never in tracked files.

Safe rollout:
1. Add `GEMINI.md`.
2. Add a minimal PR-review workflow with read-only permissions first.
3. Configure the secret in GitHub Settings → Secrets and variables → Actions.
4. Test on a documentation-only PR.
5. Only then consider on-demand code modification on isolated branches.
6. Require CI and human approval before merge; do not grant production deployment permissions.

Official references:
- https://github.com/google-github-actions/run-gemini-cli
- https://github.com/google-gemini/gemini-cli
- https://docs.github.com/en/actions

## 6. Gemini Apps attachment

Useful for interactive codebase questions where supported, but an attached repository is a snapshot. Reattach/reimport to refresh. Do not use it as the automatic synchronization mechanism.

Official reference:
- https://support.google.com/gemini/answer/16176929?hl=en-GB

## 7. Synchronization acceptance contract

Synchronization is successful only when:
- the workflow ran on the expected commit SHA;
- expected repository files were available;
- the agent reports the exact SHA/context it inspected;
- proposed changes are isolated on a branch or PR;
- CI and policy checks passed;
- no secret or protected production data was exposed;
- a human approved and merged changes where required.

A new commit to `main` updates GitHub immediately. It does not refresh a previously imported Gemini Apps snapshot or necessarily alter an already-running Gemini conversation. The next CLI/action run should check out the target commit.

## 8. Security

- Begin with read-only repository access for review workflows.
- Use minimal GitHub Actions permissions.
- Pin third-party actions to reviewed immutable versions/SHAs where practical.
- Do not give the agent deployment credentials, production database secrets, or Auth0 secrets.
- Never auto-merge AI-generated code or deploy it to production during initial rollout.
- Use protected branches and required checks where available.
- Log workflow run IDs, target commit SHA, generated PR, tests, reviewer decision, and outcome.

## 9. Acceptance tests

1. A documentation-only PR triggers the Gemini review workflow.
2. The workflow records the exact commit SHA.
3. The agent reads `GEMINI.md` and the handover file.
4. Missing credentials fail closed without leaking secrets.
5. The agent cannot write directly to `main` or deploy production.
6. Proposed changes arrive as a reviewable PR.
7. CI failure blocks merge.
8. The next workflow run checks out a new `main` commit; stale Gemini Apps attachments are explicitly treated as stale.
9. Run IDs and evidence are linked in the project record.

## 10. Human action required

A repository administrator must configure Gemini authentication in GitHub Actions Secrets (or approve an alternative identity mechanism). This documentation change cannot safely create or infer that secret. Never paste it into chat or commit it.

## 11. Current status

- Existing handover document found.
- A canonical `GEMINI.md` and verified Gemini Actions workflow were not found in the inspected repository tree on 2026-10-11.
- Gemini Apps import is not live sync.
- End-to-end automatic update behavior is NOT YET TESTED.


## 12. Repository workflow added in the audit branch

Workflow path: `.github/workflows/gemini-kaizo-context-refresh.yml` on branch `audit/kaizo-strategic-audit-gemini-sync-20261011`.

Security review found that the third-party Gemini CLI action invokes the CLI with `--yolo`; a read-only prompt is not a technical permission boundary. The workflow was therefore hardened in commit `7a97b34356181489254a924809fe4c376aa1dca0` to use the Gemini generateContent API directly rather than launching an agent CLI.

Current design:
- Triggers on pushes to `main` affecting project context/code paths, and supports manual `workflow_dispatch`.
- Checks out the exact triggering commit using a pinned checkout action SHA.
- Sends a bounded bundle of named repository files to Gemini API using the existing `GEMINI_API_KEY` secret.
- Grants only `contents: read`; no agent shell/file tools, repository write token, branch creation, PR creation, merge, or deployment permissions are granted.
- Omits error response bodies on failed API calls to reduce accidental secret/context leakage.
- Produces a Markdown status summary in the GitHub Actions run summary; it does not write back to the repository.

**Activation status:** not active on `main` yet because the workflow is part of draft PR #87. The YAML/API path has not yet been proven by a successful GitHub Actions run. The existing `GEMINI_API_KEY` secret was already confirmed by the project owner; do not ask to recreate it. This workflow refreshes context during a GitHub Actions run; it does not push updates into an already-open Gemini Apps conversation or refresh a previously imported Gemini Apps snapshot.
