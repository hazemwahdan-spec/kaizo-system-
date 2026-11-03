"""Evidence-backed, read-only Coach current-priority queue (FEAT-007).

Only explicit next-decision triggers and response records without a linked
retest are surfaced. No deadline, urgency score, task, or action is invented.
"""
from __future__ import annotations

from typing import Any

import persistence


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def build_priority_items(athletes: list[dict[str, Any]],
                         records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build transparent review signals from persisted workflow evidence."""
    names = {a["athlete_id"]: a.get("display_name", a["athlete_id"])
             for a in athletes}
    retests = {
        (r.get("athlete_id"), r.get("session_id"))
        for r in records
        if r.get("feature_id") == "FEAT-037" and r.get("session_id")
    }
    items: list[dict[str, Any]] = []
    for record in records:
        feature = record.get("feature_id")
        athlete_id = record.get("athlete_id")
        if athlete_id not in names:
            continue
        payload = _payload(record.get("payload"))
        item: dict[str, Any] | None = None
        if feature == "FEAT-040":
            reason = str(payload.get("trigger_reason") or "").strip()
            required = payload.get("required_evidence")
            if not reason or not isinstance(required, list) or not required:
                continue
            item = {
                "item_type": "EXPLICIT_NEXT_DECISION_TRIGGER",
                "title": "Review next-decision trigger",
                "reason": reason,
                "evidence_refs": [str(x) for x in required if str(x).strip()],
                "suggested_next_action": (
                    "Review the recorded trigger and its required evidence; "
                    "the Coach decides whether to open the next decision cycle."
                ),
            }
        elif feature == "FEAT-036":
            session_id = record.get("session_id")
            if not session_id or (athlete_id, session_id) in retests:
                continue
            response = payload.get("response")
            item = {
                "item_type": "RESPONSE_WITHOUT_RETEST",
                "title": "Review training response / retest",
                "reason": (
                    "A training-response record exists for this session, "
                    "but no linked FEAT-037 retest record was found."
                ),
                "evidence_refs": [str(record.get("record_id"))],
                "response_summary": str(response) if response is not None else None,
                "suggested_next_action": (
                    "Review the response evidence and decide whether a retest "
                    "is appropriate; no retest is initiated automatically."
                ),
            }
        if item is None:
            continue
        item.update({
            "item_id": str(record.get("record_id")),
            "athlete_id": athlete_id,
            "athlete_name": names[athlete_id],
            "source_feature": feature,
            "source_record_id": str(record.get("record_id")),
            "decision_id": record.get("decision_id"),
            "session_id": record.get("session_id"),
            "recorded_at": record.get("created_at"),
            "review_state": "STATUS_NOT_TRACKED",
            "priority_rank": None,
            "due_at": None,
        })
        items.append(item)
    items.sort(key=lambda x: (str(x.get("recorded_at") or ""),
                              str(x.get("item_id") or "")), reverse=True)
    return items


def get_coach_priority_queue(*, tenant_id: str, coach_actor_id: str) -> dict[str, Any]:
    """Read only workflow records attached to this verified Coach's owned athletes."""
    athletes = []
    # Import locally to avoid coupling the ownership module to queue construction.
    from productization.coach_roster import list_owned_athletes
    athletes = list_owned_athletes(tenant_id=tenant_id, coach_actor_id=coach_actor_id)
    base = {
        "source_scope": "verified_coach_tenant_owned_records",
        "coach_final_authority": True,
        "execution_authorized": False,
        "ranking_policy": "UNRANKED_NO_DEADLINE_OR_URGENCY_EVIDENCE",
        "queue_semantics": "REVIEW_SIGNALS_NOT_OPEN_TASKS",
        "review_status_policy": "Source records do not track acknowledgement or closure.",
        "time_window": "ALL_AVAILABLE_PERSISTED_RECORDS_NO_CALENDAR_DATE_FILTER",
        "due_date_policy": "No due dates are inferred.",
    }
    if not persistence.is_postgres_enabled():
        return {**base, "available": False, "status": "INSUFFICIENT_EVIDENCE",
                "items": [], "message": (
                    "The current memory adapter does not expose durable FEAT-036/037/040 "
                    "workflow records; no queue items are inferred."
                )}
    if not athletes:
        return {**base, "available": True, "status": "NO_CURRENT_ITEMS", "items": []}
    athlete_ids = [a["athlete_id"] for a in athletes]
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.kaizo_training_workflow_records')")
            if cur.fetchone()[0] is None:
                return {**base, "available": False, "status": "INSUFFICIENT_EVIDENCE",
                        "items": [], "message": (
                            "No persisted training-workflow evidence table is available."
                        )}
            cur.execute("""
                SELECT record_id, feature_id, athlete_id, decision_id, session_id,
                       payload, created_by, created_at
                FROM kaizo_training_workflow_records
                WHERE athlete_id = ANY(%s)
                  AND feature_id IN ('FEAT-036', 'FEAT-037', 'FEAT-040')
                ORDER BY created_at DESC, record_id DESC
            """, (athlete_ids,))
            rows = cur.fetchall()
    records = [{
        "record_id": r[0], "feature_id": r[1], "athlete_id": r[2],
        "decision_id": r[3], "session_id": r[4], "payload": r[5],
        "created_by": r[6], "created_at": r[7],
    } for r in rows]
    items = build_priority_items(athletes, records)
    return {**base, "available": True,
            "status": "REVIEW_SIGNALS_AVAILABLE" if items else "NO_REVIEW_SIGNALS",
            "items": items,
            "item_count": len(items)}
