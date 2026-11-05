# FEAT-008 — Coach Athlete Workflow Navigation
Status: implementation acceptance contract for Draft PR #182.

## Scope
Provide verified Coaches with a navigable path from their existing owned-athlete roster to an individual athlete's already-recorded profile, lifecycle, status history, and decision-cycle history.

## Required behavior
- Search/filter only the roster already returned by the verified `GET /coach/athletes` API; match athlete display name and athlete ID case-insensitively.
- Do not send search terms, actor identity, role, tenant, or resource-owner scope from the browser. Server-side ownership remains authoritative.
- Selecting an athlete loads the existing scoped athlete-detail endpoint and the existing scoped status-history and decision-cycle endpoints.
- Provide explicit navigation among Profile, Lifecycle, Status History, and Decision History sections, plus a return-to-roster action.
- Escape all server-returned text before HTML insertion; never treat athlete names, IDs, reasons, or decision summaries as markup.
- Empty search results, empty roster, missing history, and API/authorization errors must be explicit; errors fail closed and must not leave another athlete's previous data visible.
- Search/filter is client-side over the authenticated Coach's roster only. It does not create or modify records.
- Preserve existing audited lifecycle transitions; navigation and search themselves remain read-only.

## Governance and security
- All API requests continue to use the verified Auth0 bearer token.
- No client-supplied Coach/tenant identity headers or query parameters.
- Cross-Coach and cross-tenant access remains denied by the existing server-side ownership boundary.
- Coach Final Authority remains true; `execution_authorized=false`.
- No new data model, historical backfill, synthetic athlete, or Frozen Core/JCS change.

## Acceptance
- UI contract verifies roster search, selected-athlete navigation, return path, escaped output, and use of existing scoped endpoints only.
- Existing roster, lifecycle, status-history, and decision-history authorization/regression suites continue to pass.
- Product runtime, identity boundary, product contract, persistence regression, and FEAT-033–040 end-to-end workflows pass.
- PR remains Draft and unmerged pending Coach review.
