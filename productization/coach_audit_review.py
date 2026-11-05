"""FEAT-054: read-only audit query over verified Coach-owned action history.

The service never queries the global audit ledger directly. It delegates to the
FEAT-010 tenant/actor/athlete-scoped history boundary, then filters only those
already-authorized records.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from productization import coach_action_history


def review_coach_audit(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, query: str
) -> dict[str, Any] | None:
    term = query.strip()
    if not term:
        raise ValueError("query is required")
    if len(term) > 200:
        raise ValueError("query must be 200 characters or fewer")

    history = coach_action_history.get_coach_action_history(
        tenant_id=tenant_id,
        coach_actor_id=coach_actor_id,
        athlete_id=athlete_id,
    )
    if history is None:
        return None

    if not history.get("available"):
        results = []
        status = "INSUFFICIENT_EVIDENCE"
    else:
        needle = term.casefold()
        results = [
            item for item in history.get("items", [])
            if item.get("actor_attribution_verified") is True
            and needle in " ".join(str(item.get(key) or "") for key in (
                "source", "source_record_id", "occurred_at", "actor_id",
                "action", "reason", "decision_id", "state_version", "state_ref"
            )).casefold()
        ]
        status = "MATCHES_FOUND" if results else "NO_MATCHES"

    return {
        "feature_id": "FEAT-054",
        "athlete_id": athlete_id,
        "query": term,
        "status": status,
        "results": results,
        "result_count": len(results),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": coach_actor_id,
        "reviewed_by_verified": True,
        "source_boundary": "FEAT-010 verified Coach actor + tenant + owned athlete history",
        "read_only": True,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
