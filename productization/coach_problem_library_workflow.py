"""Protected FEAT-017 problem-library listing and assessment selection.

Only provenance-bearing, APPROVED, VERIFIED problem entries from the shared
knowledge SSOT are selectable. Selection writes are scoped to the authenticated
Coach, tenant, athlete and owned assessment, with an atomic tenant audit event.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import persistence
from . import coach_assessment_workflow, coach_roster


_MEMORY_SELECTIONS: dict[str, dict[str, Any]] = {}
_MEMORY_AUDIT: list[dict[str, Any]] = []


class CoachProblemLibraryNotFound(LookupError):
    pass


class CoachProblemLibraryConflict(RuntimeError):
    pass


def reset_memory_state() -> None:
    _MEMORY_SELECTIONS.clear()
    _MEMORY_AUDIT.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _library_items() -> dict[str, dict[str, Any]]:
    items = persistence.load_knowledge() or {}
    return {str(k): v for k, v in items.items() if isinstance(v, dict)}


def _is_approved_problem_entry(item_id: str, item: dict[str, Any]) -> bool:
    domain = str(item.get("domain") or item.get("entity_type") or item.get("type") or "").strip().lower()
    source_type = str(item.get("source_type") or "").strip().lower()
    is_problem = (
        domain == "problem"
        or source_type in {"problem", "problem_library", "problem-library"}
        or item_id.upper().startswith("PRB-")
    )
    evidence_refs = item.get("evidence_refs")
    has_provenance = all(str(item.get(key) or "").strip() for key in (
        "source_type", "source_ref", "source_version", "provenance_note", "changed_by"
    ))
    has_evidence = isinstance(evidence_refs, list) and bool(evidence_refs) and all(
        str(x).strip() for x in evidence_refs
    )
    return (
        is_problem
        and str(item.get("lifecycle_status") or "").upper() == "APPROVED"
        and str(item.get("evidence_status") or "").upper() == "VERIFIED"
        and has_provenance and has_evidence
    )


def list_approved_problem_library(*, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    normalized = str(query or "").strip().lower()
    results = []
    for item_id, item in _library_items().items():
        if not _is_approved_problem_entry(item_id, item):
            continue
        knowledge_id = str(item.get("knowledge_id") or item.get("id") or item_id)
        title = str(item.get("title") or item.get("provenance_note") or knowledge_id)
        haystack = " ".join((knowledge_id, title, str(item.get("source_ref") or ""))).lower()
        if normalized and normalized not in haystack:
            continue
        results.append({
            "knowledge_id": knowledge_id, "title": title,
            "domain": "problem", "source_type": item["source_type"],
            "source_ref": item["source_ref"], "source_version": item["source_version"],
            "provenance_note": item["provenance_note"],
            "evidence_refs": item["evidence_refs"],
            "evidence_status": item["evidence_status"],
            "lifecycle_status": item["lifecycle_status"],
            "changed_by": item["changed_by"],
            "updated_at": item.get("updated_at"),
            "coach_final_authority": True, "execution_authorized": False,
        })
    results.sort(key=lambda x: x["knowledge_id"])
    return results[:limit]


def _owned_assessment(cur: Any, *, tenant_id: str, coach_actor_id: str,
                      athlete_id: str, assessment_id: str, lock: bool = False) -> bool:
    sql = """SELECT a.assessment_id FROM kaizo_assessments a
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
             WHERE a.assessment_id=%s AND a.athlete_id=%s
               AND o.tenant_id=%s AND o.coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o,a"
    cur.execute(sql, (assessment_id, athlete_id, tenant_id, coach_actor_id))
    return cur.fetchone() is not None


def _audit(*, tenant_id: str, coach_actor_id: str, action: str,
           record: dict[str, Any], timestamp: str) -> None:
    if persistence.is_postgres_enabled():
        persistence.append_tenant_audit(
            tenant_id=tenant_id, timestamp=timestamp, who=coach_actor_id,
            action=action, old_value=None, new_value=record,
            why="Provenance-verified shared problem library item selected for an owned athlete assessment.",
        )
    else:
        _MEMORY_AUDIT.append({
            "tenant_id": tenant_id, "who": coach_actor_id, "action": action,
            "new_value": record, "timestamp": timestamp,
        })


def select_problem_library_item(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
    assessment_id: str, library_item_id: str,
) -> dict[str, Any] | None:
    library_item_id = str(library_item_id or "").strip()
    if not library_item_id:
        raise ValueError("library_item_id is required")
    item = _library_items().get(library_item_id)
    if item is None:
        raise CoachProblemLibraryNotFound("problem library item not found")
    if not _is_approved_problem_entry(library_item_id, item):
        raise CoachProblemLibraryConflict(
            "problem library item must be a provenance-bearing APPROVED and VERIFIED problem entry"
        )
    now = _now()
    record = {
        "selection_id": str(uuid.uuid4()), "athlete_id": athlete_id,
        "assessment_id": assessment_id, "library_item_id": library_item_id,
        "selected_by": coach_actor_id, "selected_at": now,
        "lifecycle_status": item["lifecycle_status"],
        "evidence_status": item["evidence_status"],
        "coach_final_authority": True, "execution_authorized": False,
    }
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                if not _owned_assessment(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, assessment_id=assessment_id, lock=True,
                ):
                    return None
                cur.execute(
                    """INSERT INTO kaizo_problem_library_selections
                       (selection_id,athlete_id,assessment_id,library_item_id,selected_by,selected_at)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (record["selection_id"], athlete_id, assessment_id,
                     library_item_id, coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_PROBLEM_LIBRARY_SELECTED", record=record, timestamp=now)
    else:
        if coach_assessment_workflow.get_assessment(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, assessment_id=assessment_id,
        ) is None:
            return None
        _MEMORY_SELECTIONS[record["selection_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_PROBLEM_LIBRARY_SELECTED", record=record, timestamp=now)
    return record


def list_problem_library_selections(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
    assessment_id: str,
) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if not _owned_assessment(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, assessment_id=assessment_id,
                ):
                    return None
                cur.execute(
                    """SELECT s.selection_id,s.athlete_id,s.assessment_id,s.library_item_id,
                              s.selected_by,s.selected_at
                       FROM kaizo_problem_library_selections s
                       JOIN kaizo_assessments a ON a.assessment_id=s.assessment_id
                         AND a.athlete_id=s.athlete_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=s.athlete_id
                       WHERE s.athlete_id=%s AND s.assessment_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY s.selected_at,s.selection_id""",
                    (athlete_id, assessment_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "selection_id": x[0], "athlete_id": x[1], "assessment_id": x[2],
            "library_item_id": x[3], "selected_by": x[4], "selected_at": x[5],
            "coach_final_authority": True, "execution_authorized": False,
        } for x in rows]
    if coach_assessment_workflow.get_assessment(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, assessment_id=assessment_id,
    ) is None:
        return None
    return sorted(
        [x for x in _MEMORY_SELECTIONS.values()
         if x["athlete_id"] == athlete_id and x["assessment_id"] == assessment_id],
        key=lambda x: (x["selected_at"], x["selection_id"]),
    )


def get_problem_library_selection(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
    assessment_id: str, selection_id: str,
) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if not _owned_assessment(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, assessment_id=assessment_id,
                ):
                    return None
                cur.execute(
                    """SELECT s.selection_id,s.athlete_id,s.assessment_id,s.library_item_id,
                              s.selected_by,s.selected_at
                       FROM kaizo_problem_library_selections s
                       JOIN kaizo_assessments a ON a.assessment_id=s.assessment_id
                         AND a.athlete_id=s.athlete_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=s.athlete_id
                       WHERE s.selection_id=%s AND s.athlete_id=%s AND s.assessment_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s""",
                    (selection_id, athlete_id, assessment_id, tenant_id, coach_actor_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "selection_id": row[0], "athlete_id": row[1], "assessment_id": row[2],
            "library_item_id": row[3], "selected_by": row[4], "selected_at": row[5],
            "coach_final_authority": True, "execution_authorized": False,
        }
    selections = list_problem_library_selections(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, assessment_id=assessment_id,
    )
    if selections is None:
        return None
    return next((x for x in selections if x["selection_id"] == selection_id), None)
