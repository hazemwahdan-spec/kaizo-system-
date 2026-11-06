"""FEAT-010: verified Coach action history over explicit tenant-owned records.

Only audit rows carrying the verified tenant and Coach actor are attributed to
that Coach. FEAT-044 state links are included as related lineage, but their
client-supplied linked_by field is deliberately not treated as verified actor
identity.
"""
from __future__ import annotations

from typing import Any

import persistence
from productization import coach_roster


def _empty(status: str, message: str, *, available: bool = False) -> dict[str, Any]:
    return {
        "available": available,
        "status": status,
        "message": message,
        "items": [],
        "item_count": 0,
        "sources": ["kaizo_audit_logs", "kaizo_decision_records", "kaizo_decision_state_links"],
        "read_only": True,
        "coach_final_authority": True,
        "execution_authorized": False,
    }


def get_coach_action_history(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str
) -> dict[str, Any] | None:
    """Return only this verified Coach's tenant-scoped events for an owned athlete."""
    athlete = coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    )
    if athlete is None:
        return None

    if not persistence.is_postgres_enabled():
        return _empty(
            "INSUFFICIENT_EVIDENCE",
            "Coach action history requires durable tenant-scoped audit and FEAT-044 state-link records.",
        )

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT to_regclass('public.kaizo_audit_logs'),
                       to_regclass('public.kaizo_decision_records'),
                       to_regclass('public.kaizo_decision_state_links'),
                       to_regclass('public.kaizo_coach_athlete_ownership')
            """)
            tables = cur.fetchone()
            if not tables or any(table is None for table in tables):
                return _empty(
                    "INSUFFICIENT_EVIDENCE",
                    "Required durable audit, decision, ownership, or FEAT-044 state-link records are unavailable.",
                )

            cur.execute("""
                SELECT a.id, a.timestamp, a.who, a.action, a.why,
                       COALESCE(a.new_value->>'decision_id', a.old_value->>'decision_id')
                FROM kaizo_audit_logs a
                WHERE a.tenant_id=%s
                  AND a.who=%s
                  AND (
                    a.new_value->>'athlete_id'=%s
                    OR a.old_value->>'athlete_id'=%s
                    OR COALESCE(a.new_value->>'decision_id', a.old_value->>'decision_id') IN (
                        SELECT d.decision_id
                        FROM kaizo_decision_records d
                        JOIN kaizo_coach_athlete_ownership owned
                          ON owned.athlete_id=d.athlete_id
                         AND owned.tenant_id=%s
                         AND owned.coach_actor_id=%s
                        WHERE d.athlete_id=%s
                    )
                  )
                ORDER BY a.timestamp DESC, a.id DESC
            """, (
                tenant_id, coach_actor_id, athlete_id, athlete_id,
                tenant_id, coach_actor_id, athlete_id,
            ))
            audit_rows = cur.fetchall()

            # FEAT-044 does not authenticate linked_by. A link is shown only
            # when both its decision and entity resolve to this owned athlete;
            # the actor is intentionally omitted and marked unverified.
            cur.execute("""
                SELECT l.link_id, l.decision_id, l.state_version, l.state_ref, l.linked_at
                FROM kaizo_decision_state_links l
                JOIN kaizo_decision_records d
                  ON d.decision_id=l.decision_id
                 AND d.athlete_id=%s
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=d.athlete_id
                 AND owned.tenant_id=%s
                 AND owned.coach_actor_id=%s
                WHERE l.entity_id=%s
                ORDER BY l.linked_at DESC, l.link_id DESC
            """, (athlete_id, tenant_id, coach_actor_id, athlete_id))
            link_rows = cur.fetchall()

    items = [{
        "source": "TENANT_SCOPED_AUDIT",
        "source_record_id": str(row[0]),
        "occurred_at": row[1],
        "actor_id": row[2],
        "actor_attribution_verified": True,
        "action": row[3],
        "reason": row[4],
        "decision_id": row[5],
    } for row in audit_rows]

    items.extend({
        "source": "FEAT-044_DECISION_STATE_LINK",
        "source_record_id": row[0],
        "occurred_at": row[4],
        "actor_id": None,
        "actor_attribution_verified": False,
        "action": "DECISION_STATE_LINK_RECORDED",
        "reason": "Related state linkage; FEAT-044 linked_by is not verified as Coach identity.",
        "decision_id": row[1],
        "state_version": row[2],
        "state_ref": row[3],
    } for row in link_rows)

    items.sort(key=lambda item: (str(item.get("occurred_at") or ""), str(item.get("source_record_id") or "")), reverse=True)
    return {
        "available": True,
        "status": "ACTION_HISTORY_AVAILABLE" if items else "NO_RECORDED_ACTIONS",
        "message": None if items else "No attributable Coach actions or linked state records were found for this athlete.",
        "items": items,
        "item_count": len(items),
        "sources": ["tenant_scoped_kaizo_audit_logs", "owned_decision_records", "FEAT-044_decision_state_links"],
        "read_only": True,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
