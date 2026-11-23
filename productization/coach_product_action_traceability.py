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


def _visible_source_ids(history: dict[str, Any]) -> set[str]:
    return {
        str(item.get("source_record_id"))
        for item in history.get("items", [])
        if item.get("actor_attribution_verified") is True
        and item.get("source_record_id") is not None
    }


def _lock_verified_source_rows(
    cur: Any, *, tenant_id: str, coach_actor_id: str,
    athlete_id: str, source_record_ids: list[str],
) -> bool:
    """Lock the exact tenant/Coach/athlete audit rows used as trace sources."""
    try:
        numeric_ids = [int(item) for item in source_record_ids]
    except (TypeError, ValueError):
        return False
    cur.execute(
        """SELECT a.id
           FROM kaizo_audit_logs a
           WHERE a.id = ANY(%s)
             AND a.tenant_id=%s AND a.who=%s
             AND (
               a.new_value->>'athlete_id'=%s
               OR a.old_value->>'athlete_id'=%s
               OR COALESCE(a.new_value->>'decision_id',a.old_value->>'decision_id') IN (
                   SELECT d.decision_id
                   FROM kaizo_decision_records d
                   JOIN kaizo_coach_athlete_ownership owned
                     ON owned.athlete_id=d.athlete_id
                    AND owned.tenant_id=%s
                    AND owned.coach_actor_id=%s
                   WHERE d.athlete_id=%s AND d.coach_id=%s
               )
             )
           FOR SHARE OF a""",
        (numeric_ids, tenant_id, coach_actor_id, athlete_id, athlete_id,
         tenant_id, coach_actor_id, athlete_id, coach_actor_id),
    )
    return {str(row[0]) for row in cur.fetchall()} == set(source_record_ids)


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

    # Fast pre-check for useful error messages. These values are re-read under
    # row locks below; this first read is never the final write authorization.
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
    unknown_ids = sorted(set(source_ids) - _visible_source_ids(history))
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
    with persistence.atomic_transaction() as conn:
        # Lock ownership first. A concurrent Coach transfer/reassignment must
        # wait until the trace and its tenant audit either commit or roll back.
        with conn.cursor() as cur:
            cur.execute(
                """SELECT athlete_id FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                   FOR UPDATE""",
                (tenant_id, coach_actor_id, athlete_id),
            )
            if cur.fetchone() is None:
                return None

        # Revalidate ownership and source history inside the same transaction.
        if coach_roster.get_owned_athlete(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
        ) is None:
            return None
        current_history = coach_action_history.get_coach_action_history(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
        )
        if not current_history or not current_history.get("available"):
            return {
                "feature_id": "FEAT-055", "status": "INSUFFICIENT_EVIDENCE",
                "message": "Durable verified Coach action history is unavailable.",
                "created": False, "read_only": True, "coach_final_authority": True,
                "execution_authorized": False,
            }
        current_visible_ids = _visible_source_ids(current_history)
        if set(source_ids) - current_visible_ids:
            raise ValueError("Every source_record_id must remain in this Coach-owned athlete history")

        result = {
            "feature_id": "FEAT-055", "trace_id": str(uuid4()),
            "tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
            "athlete_id": athlete_id, "product_action": action,
            "source_record_ids": source_ids, "trace_reason": reason,
            "traced_at": traced_at, "status": "TRACE_RECORDED",
            "created": True, "source_scope_verified": True,
            "coach_final_authority": True, "execution_authorized": False,
        }
        with conn.cursor() as cur:
            if not _lock_verified_source_rows(
                cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                athlete_id=athlete_id, source_record_ids=source_ids,
            ):
                raise ValueError("Every source_record_id must remain a tenant/Coach/athlete audit record")
            cur.execute(
                """INSERT INTO kaizo_coach_product_action_traces
                   (trace_id,tenant_id,coach_actor_id,athlete_id,product_action,
                    source_record_ids,trace_reason,traced_at)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                (result["trace_id"], tenant_id, coach_actor_id, athlete_id,
                 action, json.dumps(source_ids), reason, traced_at),
            )
        persistence.append_tenant_audit(
            tenant_id=tenant_id, timestamp=traced_at, who=coach_actor_id,
            action="FEAT-055_PRODUCT_ACTION_TRACE_RECORDED",
            old_value=None, new_value=result,
            why="Product action linked to locked, verified Coach-owned source records; trace and audit commit atomically.",
        )
    return result


def list_coach_product_action_traces(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str
) -> dict[str, Any] | None:
    if not persistence.is_postgres_enabled():
        athlete = coach_roster.get_owned_athlete(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
        )
        if athlete is None:
            return None
        return {
            "feature_id": "FEAT-055", "athlete_id": athlete_id,
            "status": "INSUFFICIENT_EVIDENCE", "items": [], "total": 0,
            "message": "Durable PostgreSQL trace storage is unavailable.",
            "read_only": True, "coach_final_authority": True,
            "execution_authorized": False,
        }

    # Authorization and the trace read share one transaction. Holding the
    # ownership row lock prevents a concurrent reassignment from exposing
    # history after the caller has lost this Coach/tenant/athlete scope.
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT athlete_id FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                   FOR KEY SHARE""",
                (tenant_id, coach_actor_id, athlete_id),
            )
            if cur.fetchone() is None:
                return None
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
