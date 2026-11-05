"""FEAT-055: durable Coach-scoped product-action traceability.

A Coach may link a product action only to source records already visible in that
Coach's verified FEAT-010 action history for the same owned athlete. Actor,
tenant, and athlete scope are derived server-side. No caller-supplied actor
identity is accepted by this service.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import persistence
from productization import coach_action_history, coach_roster


def create_coach_product_action_trace(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
    product_action: str, source_record_ids: list[str], trace_reason: str,
) -> dict[str, Any] | None:
    action = product_action.strip()
    reason = trace_reason.strip()
    source_ids = [item.strip() for item in source_record_ids if isinstance(item, str)]
    if not action or len(action) > 120:
        raise ValueError("product_action must contain 1-120 characters")
    if not reason or len(reason) > 1000:
        raise ValueError("trace_reason must contain 1-1000 characters")
    if not source_ids or any(not item for item in source_ids):
        raise ValueError("source_record_ids must be a non-empty list of non-empty IDs")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source_record_ids must not contain duplicates")
    if len(source_ids) > 100:
        raise ValueError("source_record_ids cannot exceed 100 entries")

    athlete = coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    )
    if athlete is None:
        return None

    history = coach_action_history.get_coach_action_history(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    )
    if not history or not history.get("available"):
        return {
            "feature_id": "FEAT-055", "status": "INSUFFICIENT_EVIDENCE",
            "message": "Durable verified Coach action history is unavailable.",
            "created": False, "read_only": True, "coach_final_authority": True,
            "execution_authorized": False,
        }

    visible_ids = {
        str(item.get("source_record_id"))
        for item in history.get("items", [])
        if item.get("actor_attribution_verified") is True
        and item.get("source_record_id") is not None
    }
    unknown_ids = sorted(set(source_ids) - visible_ids)
    if unknown_ids:
        raise ValueError("Every source_record_id must exist in this Coach-owned athlete history")

    if not persistence.is_postgres_enabled():
        return {
            "feature_id": "FEAT-055", "status": "INSUFFICIENT_EVIDENCE",
            "message": "Durable PostgreSQL storage is required; no trace was written.",
            "created": False, "read_only": True, "coach_final_authority": True,
            "execution_authorized": False,
        }

    traced_at = datetime.now(timezone.utc).isoformat()
    result = {
        "feature_id": "FEAT-055", "trace_id": str(uuid4()),
        "tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
        "athlete_id": athlete_id, "product_action": action,
        "source_record_ids": source_ids, "trace_reason": reason,
        "traced_at": traced_at, "status": "TRACE_RECORDED",
        "created": True, "source_scope_verified": True,
        "coach_final_authority": True, "execution_authorized": False,
    }
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kaizo_coach_product_action_traces
                    (trace_id, tenant_id, coach_actor_id, athlete_id,
                     product_action, source_record_ids, trace_reason, traced_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """, (result["trace_id"], tenant_id, coach_actor_id, athlete_id,
                  action, json.dumps(source_ids), reason, traced_at))
        conn.commit()
    return result


def list_coach_product_action_traces(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str
) -> dict[str, Any] | None:
    athlete = coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    )
    if athlete is None:
        return None
    if not persistence.is_postgres_enabled():
        return {
            "feature_id": "FEAT-055", "athlete_id": athlete_id,
            "status": "INSUFFICIENT_EVIDENCE", "items": [], "total": 0,
            "message": "Durable PostgreSQL trace storage is unavailable.",
            "read_only": True, "coach_final_authority": True,
            "execution_authorized": False,
        }
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.kaizo_coach_product_action_traces')")
            table = cur.fetchone()
            if not table or table[0] is None:
                return {
                    "feature_id": "FEAT-055", "athlete_id": athlete_id,
                    "status": "INSUFFICIENT_EVIDENCE", "items": [], "total": 0,
                    "message": "Durable trace storage has not been initialized.",
                    "read_only": True, "coach_final_authority": True,
                    "execution_authorized": False,
                }
            cur.execute("""
                SELECT trace_id, product_action, source_record_ids,
                       trace_reason, traced_at
                FROM kaizo_coach_product_action_traces
                WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                ORDER BY traced_at DESC, trace_id DESC
            """, (tenant_id, coach_actor_id, athlete_id))
            rows = cur.fetchall()
    items = [{
        "trace_id": row[0], "product_action": row[1],
        "source_record_ids": row[2], "trace_reason": row[3],
        "traced_at": row[4],
    } for row in rows]
    return {
        "feature_id": "FEAT-055", "athlete_id": athlete_id,
        "status": "TRACE_HISTORY_AVAILABLE" if items else "NO_TRACES",
        "items": items, "total": len(items), "read_only": True,
        "coach_final_authority": True, "execution_authorized": False,
    }
