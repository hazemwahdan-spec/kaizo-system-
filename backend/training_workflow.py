"""Ownership-scoped, auditable FEAT-033..040 Coach workflow.

Every request requires a verified Coach principal (OIDC in production) and a
server-side ownership lookup. Caller-supplied actor identifiers are ignored.
Training record and tenant-scoped audit event are committed in one transaction.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

import persistence
from productization import coach_roster, coach_training_workflow, coach_progression_workflow, coach_decision_workflow, coach_assessment_workflow
from productization.product_api import verified_coach_scope

router = APIRouter(prefix="/api/v1/training-workflow", tags=["training-workflow"])

_MEMORY_RECORDS: list[dict[str, Any]] = []
_MEMORY_AUDIT: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coach_for_athlete(
    athlete_id: str,
    authorization: str | None,
    actor_id: str | None,
    role: str | None,
    tenant_id: str | None,
    owner: str | None,
):
    # verified_coach_scope uses JWT issuer/audience/JWKS validation in OIDC mode.
    # Development headers are accepted only when KAIZO_IDENTITY_MODE=development.
    principal = verified_coach_scope(authorization, actor_id, role, tenant_id, owner)
    if not persistence.is_postgres_enabled() and principal.verified:
        raise HTTPException(status_code=503, detail="durable Coach workflow requires PostgreSQL")
    athlete = coach_roster.get_owned_athlete(
        tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id,
        athlete_id=athlete_id,
    )
    if athlete is None:
        # Avoid disclosing whether an athlete exists in another Coach/tenant scope.
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return principal


def _ensure_schema() -> None:
    """Compatibility no-op; persistence.initialize() owns all feature DDL."""
    return None


def _save(
    feature_id: str,
    athlete_id: str,
    payload: Dict[str, Any],
    principal: Any,
    decision_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload = dict(payload)
    # Client-supplied authority flags are never authoritative; this value is derived
    # from the verified Coach principal that passed _coach_for_athlete.
    payload["coach_final_authority"] = True
    payload["execution_authorized"] = False
    record = {
        "record_id": str(uuid4()),
        "feature_id": feature_id,
        "athlete_id": athlete_id,
        "tenant_id": principal.tenant_id,
        "coach_actor_id": principal.actor_id,
        "decision_id": decision_id,
        "session_id": session_id,
        "payload": payload,
        "created_by": principal.actor_id,
        "created_at": _now(),
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    audit = {
        "timestamp": record["created_at"],
        "who": principal.actor_id,
        "action": f"{feature_id}_RECORDED",
        "old_value": None,
        "new_value": record,
        "why": "Training workflow record persisted under verified Coach ownership and Coach Final Authority.",
        "tenant_id": principal.tenant_id,
    }

    if persistence.is_postgres_enabled():
        # Schema is provisioned by persistence.initialize(); requests never run DDL.
        # Lock the authoritative ownership row in the same transaction as both
        # the workflow record and its tenant-scoped audit event. A concurrent
        # ownership removal/transfer must wait until this write commits.
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_coach_athlete_ownership
                       WHERE athlete_id=%s AND tenant_id=%s AND coach_actor_id=%s
                       FOR UPDATE""",
                    (athlete_id, principal.tenant_id, principal.actor_id),
                )
                if cur.fetchone() is None:
                    raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
                decision_id, session_id = _validate_lineage_sql(
                    cur, feature_id=feature_id, athlete_id=athlete_id, principal=principal,
                    payload=payload, decision_id=decision_id, session_id=session_id,
                )
                record["decision_id"] = decision_id
                record["session_id"] = session_id
                cur.execute(
                    """INSERT INTO kaizo_training_workflow_records
                    (record_id,feature_id,athlete_id,decision_id,session_id,payload,
                     created_by,created_at,coach_final_authority,execution_authorized,
                     tenant_id,coach_actor_id)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)""",
                    (
                        record["record_id"], feature_id, athlete_id, decision_id,
                        session_id, json.dumps(payload), principal.actor_id,
                        record["created_at"], True, False,
                        principal.tenant_id, principal.actor_id,
                    ),
                )
            persistence.append_tenant_audit(
                tenant_id=audit["tenant_id"],
                timestamp=audit["timestamp"],
                who=audit["who"],
                action=audit["action"],
                old_value=audit["old_value"],
                new_value=audit["new_value"],
                why=audit["why"],
            )
    else:
        # Explicitly development/test-only adapter. Production OIDC is refused
        # above unless durable PostgreSQL is active.
        decision_id, session_id = _validate_lineage_memory(
            feature_id=feature_id, athlete_id=athlete_id, principal=principal,
            payload=payload, decision_id=decision_id, session_id=session_id,
        )
        record["decision_id"] = decision_id
        record["session_id"] = session_id
        _MEMORY_RECORDS.append(record)
        _MEMORY_AUDIT.append(audit)
    return record


def _list(feature_id: str, athlete_id: str, tenant_id: str, coach_actor_id: str) -> List[Dict[str, Any]]:
    if not persistence.is_postgres_enabled():
        return [
            dict(item) for item in _MEMORY_RECORDS
            if item["feature_id"] == feature_id
            and item["athlete_id"] == athlete_id
            and item["tenant_id"] == tenant_id
            and item["coach_actor_id"] == coach_actor_id
        ]
    # Read paths must never initialize or mutate schema; migrations/writes own DDL.
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT r.record_id,r.feature_id,r.athlete_id,r.decision_id,r.session_id,
                          r.payload,r.created_by,r.created_at,r.coach_final_authority,
                          r.execution_authorized,r.tenant_id,r.coach_actor_id
                   FROM kaizo_training_workflow_records r
                   JOIN kaizo_coach_athlete_ownership o
                     ON o.athlete_id=r.athlete_id
                    AND o.tenant_id=r.tenant_id
                    AND o.coach_actor_id=r.coach_actor_id
                   WHERE r.feature_id=%s AND r.athlete_id=%s
                     AND r.tenant_id=%s AND r.coach_actor_id=%s
                   ORDER BY r.created_at,r.record_id""",
                (feature_id, athlete_id, tenant_id, coach_actor_id),
            )
            rows = cur.fetchall()
    return [{
        "record_id": r[0], "feature_id": r[1], "athlete_id": r[2],
        "decision_id": r[3], "session_id": r[4], "payload": r[5],
        "created_by": r[6], "created_at": r[7],
        "coach_final_authority": r[8], "execution_authorized": r[9],
        "tenant_id": r[10], "coach_actor_id": r[11],
    } for r in rows]


def reset_memory_state() -> None:
    """Test helper; clears only the isolated in-memory adapter."""
    _MEMORY_RECORDS.clear()
    _MEMORY_AUDIT.clear()


def _parent_record_sql(cur: Any, *, record_id: str, feature_id: str,
                       athlete_id: str, principal: Any) -> Dict[str, Any]:
    cur.execute(
        """SELECT r.record_id,r.feature_id,r.athlete_id,r.decision_id,r.session_id,
                  r.payload,r.created_by,r.created_at
           FROM kaizo_training_workflow_records r
           JOIN kaizo_coach_athlete_ownership o
             ON o.athlete_id=r.athlete_id AND o.tenant_id=r.tenant_id
            AND o.coach_actor_id=r.coach_actor_id
           WHERE r.record_id=%s AND r.feature_id=%s AND r.athlete_id=%s
             AND r.tenant_id=%s AND r.coach_actor_id=%s
           FOR SHARE OF r""",
        (record_id, feature_id, athlete_id, principal.tenant_id, principal.actor_id),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{feature_id} record not found in Coach scope")
    return {
        "record_id": row[0], "feature_id": row[1], "athlete_id": row[2],
        "decision_id": row[3], "session_id": row[4], "payload": row[5],
        "created_by": row[6], "created_at": row[7],
    }


def _parent_record_memory(*, record_id: str, feature_id: str,
                          athlete_id: str, principal: Any) -> Dict[str, Any]:
    for item in _MEMORY_RECORDS:
        if (item.get("record_id") == record_id and item.get("feature_id") == feature_id
                and item.get("athlete_id") == athlete_id
                and item.get("tenant_id") == principal.tenant_id
                and item.get("coach_actor_id") == principal.actor_id):
            return dict(item)
    raise HTTPException(status_code=404, detail=f"{feature_id} record not found in Coach scope")


def _decision_context_sql(cur: Any, *, decision_id: str, athlete_id: str,
                          principal: Any) -> Dict[str, Any]:
    decision = coach_training_workflow._decision_sql(
        cur, tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id, decision_id=decision_id, lock=True,
    )
    if decision is None:
        raise HTTPException(status_code=404, detail="recorded Coach decision not found in athlete scope")
    return decision


def _decision_context_memory(*, decision_id: str, athlete_id: str,
                             principal: Any) -> Dict[str, Any]:
    decision = coach_training_workflow._memory_decision(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id, decision_id=decision_id,
    )
    if decision is None:
        raise HTTPException(status_code=404, detail="recorded Coach decision not found in athlete scope")
    return decision


def _session_context_sql(cur: Any, *, session_id: str, athlete_id: str,
                         principal: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    session = coach_training_workflow._session_sql(
        cur, tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id, session_id=session_id, lock=True,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="training session not found in Coach scope")
    plan = coach_training_workflow._plan_sql(
        cur, tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id, plan_id=session["plan_id"], lock=True,
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="training plan not found in Coach scope")
    decision = _decision_context_sql(
        cur, decision_id=plan["decision_id"], athlete_id=athlete_id, principal=principal,
    )
    return session, decision


def _session_context_memory(*, session_id: str, athlete_id: str,
                            principal: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    session = coach_training_workflow._memory_session(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id, session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="training session not found in Coach scope")
    plan = coach_training_workflow._memory_plan(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id, plan_id=session["plan_id"],
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="training plan not found in Coach scope")
    decision = _decision_context_memory(
        decision_id=plan["decision_id"], athlete_id=athlete_id, principal=principal,
    )
    return session, decision


def _validate_drill_sql(cur: Any, *, drill_id: str, athlete_id: str,
                        decision: Dict[str, Any], principal: Any) -> None:
    drill = coach_progression_workflow._drill_sql(
        cur, tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        drill_id=drill_id, lock=True,
    )
    if (drill is None or drill.get("status") != "PUBLISHED"
            or not drill.get("coach_review")
            or drill.get("source_assessment_id") != decision["assessment_id"]):
        raise HTTPException(status_code=404, detail="Coach-reviewed drill not found in decision scope")
    cur.execute(
        """SELECT evidence_ids FROM kaizo_coach_problem_drill_links
           WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
             AND problem_id=%s AND drill_id=%s AND assessment_id=%s
           FOR SHARE""",
        (principal.tenant_id, principal.actor_id, athlete_id,
         decision["problem_id"], drill_id, decision["assessment_id"]),
    )
    link = cur.fetchone()
    if link is None:
        raise HTTPException(status_code=409, detail="drill is not linked to the decision problem")
    _validate_evidence_sql(cur, drill.get("payload", {}).get("evidence", []),
                           athlete_id=athlete_id, decision=decision)
    _validate_evidence_sql(cur, link[0] or [], athlete_id=athlete_id, decision=decision)


def _validate_drill_memory(*, drill_id: str, athlete_id: str,
                           decision: Dict[str, Any], principal: Any) -> None:
    drill = coach_progression_workflow._memory_drill(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id, drill_id=drill_id,
    )
    if (drill is None or drill.get("status") != "PUBLISHED"
            or not drill.get("coach_review")
            or drill.get("source_assessment_id") != decision["assessment_id"]):
        raise HTTPException(status_code=404, detail="Coach-reviewed drill not found in decision scope")
    linked = any(
        item.get("tenant_id") == principal.tenant_id
        and item.get("coach_actor_id") == principal.actor_id
        and item.get("athlete_id") == athlete_id
        and item.get("problem_id") == decision["problem_id"]
        and item.get("drill_id") == drill_id
        and item.get("assessment_id") == decision["assessment_id"]
        for item in coach_progression_workflow._MEMORY_LINKS.values()
    )
    if not linked:
        raise HTTPException(status_code=409, detail="drill is not linked to the decision problem")
    _validate_evidence_memory(drill.get("payload", {}).get("evidence", []),
                              athlete_id=athlete_id, decision=decision)
    link = next(
        item for item in coach_progression_workflow._MEMORY_LINKS.values()
        if item.get("tenant_id") == principal.tenant_id
        and item.get("coach_actor_id") == principal.actor_id
        and item.get("athlete_id") == athlete_id
        and item.get("problem_id") == decision["problem_id"]
        and item.get("drill_id") == drill_id
        and item.get("assessment_id") == decision["assessment_id"]
    )
    _validate_evidence_memory(link.get("evidence_ids", []),
                              athlete_id=athlete_id, decision=decision)


def _validate_evidence_sql(cur: Any, evidence_ids: list[str], *,
                           athlete_id: str, decision: Dict[str, Any]) -> None:
    if not evidence_ids:
        raise HTTPException(status_code=400, detail="at least one evidence reference is required")
    for evidence_id in evidence_ids:
        try:
            coach_decision_workflow._evidence_sql(
                cur, evidence_id=evidence_id, athlete_id=athlete_id,
                problem_id=decision["problem_id"], assessment_id=decision["assessment_id"],
            )
        except coach_decision_workflow.CoachDecisionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except coach_decision_workflow.CoachDecisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def _validate_evidence_memory(evidence_ids: list[str], *,
                              athlete_id: str, decision: Dict[str, Any]) -> None:
    if not evidence_ids:
        raise HTTPException(status_code=400, detail="at least one evidence reference is required")
    for evidence_id in evidence_ids:
        try:
            coach_decision_workflow._evidence_memory(
                evidence_id=evidence_id, athlete_id=athlete_id,
                problem_id=decision["problem_id"], assessment_id=decision["assessment_id"],
            )
        except coach_decision_workflow.CoachDecisionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except coach_decision_workflow.CoachDecisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def _baseline_measurements_sql(cur: Any, *, baseline_reference: str,
                               athlete_id: str, decision: Dict[str, Any]) -> Dict[str, Any]:
    if baseline_reference == decision["assessment_id"]:
        cur.execute(
            """SELECT measurements FROM kaizo_assessments
               WHERE assessment_id=%s AND athlete_id=%s FOR SHARE""",
            (baseline_reference, athlete_id),
        )
    else:
        cur.execute(
            """SELECT measurements FROM kaizo_state_snapshots
               WHERE snapshot_id=%s AND athlete_id=%s AND assessment_id=%s FOR SHARE""",
            (baseline_reference, athlete_id, decision["assessment_id"]),
        )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="baseline reference is not linked to this athlete and decision assessment")
    return row[0]


def _baseline_measurements_memory(*, baseline_reference: str, athlete_id: str,
                                  decision: Dict[str, Any]) -> Dict[str, Any]:
    assessment = coach_assessment_workflow._MEMORY_ASSESSMENTS.get(baseline_reference)
    if assessment is not None and assessment.get("athlete_id") == athlete_id:
        if baseline_reference == decision["assessment_id"]:
            return assessment["measurements"]
    snapshot = coach_assessment_workflow._MEMORY_SNAPSHOTS.get(baseline_reference)
    if (snapshot is not None and snapshot.get("athlete_id") == athlete_id
            and snapshot.get("assessment_id") == decision["assessment_id"]):
        return snapshot["measurements"]
    raise HTTPException(status_code=404, detail="baseline reference is not linked to this athlete and decision assessment")


def _validate_retest_metric_continuity(*, response_payload: Dict[str, Any],
                                       retest_values: Dict[str, Any],
                                       baseline_measurements: Dict[str, Any]) -> None:
    """Require a retest to measure the same KPIs observed in the linked response and baseline."""
    response_metrics = set((response_payload.get("kpi_values") or {}).keys())
    retest_metrics = set((retest_values or {}).keys())
    baseline_metrics = set((baseline_measurements or {}).keys())
    if not response_metrics or retest_metrics != response_metrics:
        raise HTTPException(
            status_code=409,
            detail="retest metrics must exactly match the linked training response KPIs",
        )
    if not response_metrics.issubset(baseline_metrics):
        raise HTTPException(
            status_code=409,
            detail="retest metrics must exist in the linked baseline assessment",
        )


def _validate_lineage_sql(cur: Any, *, feature_id: str, athlete_id: str,
                          principal: Any, payload: Dict[str, Any],
                          decision_id: str | None, session_id: str | None) -> tuple[str, str | None]:
    decision: Dict[str, Any]
    if feature_id == "FEAT-033":
        if not decision_id:
            raise HTTPException(status_code=400, detail="decision_id is required")
        decision = _decision_context_sql(cur, decision_id=decision_id, athlete_id=athlete_id, principal=principal)
        _validate_drill_sql(cur, drill_id=payload["drill_id"], athlete_id=athlete_id,
                            decision=decision, principal=principal)
        _validate_evidence_sql(cur, payload.get("evidence_refs", []), athlete_id=athlete_id, decision=decision)
        return decision["decision_id"], None

    if feature_id == "FEAT-034":
        if not decision_id or not session_id:
            raise HTTPException(status_code=400, detail="decision_id and session_id are required")
        decision = _decision_context_sql(cur, decision_id=decision_id, athlete_id=athlete_id, principal=principal)
        session, session_decision = _session_context_sql(cur, session_id=session_id, athlete_id=athlete_id, principal=principal)
        if session_decision["decision_id"] != decision["decision_id"]:
            raise HTTPException(status_code=409, detail="session does not belong to the supplied decision")
        selection = _parent_record_sql(cur, record_id=payload["selection_record_id"],
                                       feature_id="FEAT-033", athlete_id=athlete_id, principal=principal)
        if (selection["decision_id"] != decision["decision_id"] or selection["session_id"] is not None
                or selection["payload"].get("drill_id") != payload["drill_id"]):
            raise HTTPException(status_code=409, detail="prescription must reference the selected drill for this decision")
        _validate_drill_sql(cur, drill_id=payload["drill_id"], athlete_id=athlete_id,
                            decision=decision, principal=principal)
        return decision["decision_id"], session["session_id"]

    if feature_id in {"FEAT-035", "FEAT-036", "FEAT-037"}:
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        session, decision = _session_context_sql(cur, session_id=session_id, athlete_id=athlete_id, principal=principal)
        if feature_id == "FEAT-035":
            prescription = _parent_record_sql(cur, record_id=payload["prescription_record_id"],
                                              feature_id="FEAT-034", athlete_id=athlete_id, principal=principal)
            if (prescription["decision_id"] != decision["decision_id"]
                    or prescription["session_id"] != session_id
                    or prescription["payload"].get("drill_id") != payload["drill_id"]):
                raise HTTPException(status_code=409, detail="execution cues must reference the matching prescription and drill")
            _validate_drill_sql(cur, drill_id=payload["drill_id"], athlete_id=athlete_id,
                                decision=decision, principal=principal)
        elif feature_id == "FEAT-036":
            cues = _parent_record_sql(cur, record_id=payload["cue_record_id"],
                                      feature_id="FEAT-035", athlete_id=athlete_id, principal=principal)
            if cues["decision_id"] != decision["decision_id"] or cues["session_id"] != session_id:
                raise HTTPException(status_code=409, detail="training response must reference execution cues from this session")
            prescription = _parent_record_sql(
                cur, record_id=cues["payload"].get("prescription_record_id", ""),
                feature_id="FEAT-034", athlete_id=athlete_id, principal=principal,
            )
            if (prescription["decision_id"] != decision["decision_id"]
                    or prescription["session_id"] != session_id
                    or prescription["payload"].get("drill_id") != cues["payload"].get("drill_id")):
                raise HTTPException(status_code=409, detail="execution cue prescription lineage is inconsistent")
            _validate_drill_sql(cur, drill_id=prescription["payload"]["drill_id"],
                                athlete_id=athlete_id, decision=decision, principal=principal)
        else:
            response = _parent_record_sql(cur, record_id=payload["response_record_id"],
                                          feature_id="FEAT-036", athlete_id=athlete_id, principal=principal)
            if response["decision_id"] != decision["decision_id"] or response["session_id"] != session_id:
                raise HTTPException(status_code=409, detail="retest must reference a response from this session")
            cues = _parent_record_sql(
                cur, record_id=response["payload"].get("cue_record_id", ""),
                feature_id="FEAT-035", athlete_id=athlete_id, principal=principal,
            )
            prescription = _parent_record_sql(
                cur, record_id=cues["payload"].get("prescription_record_id", ""),
                feature_id="FEAT-034", athlete_id=athlete_id, principal=principal,
            )
            if (cues["decision_id"] != decision["decision_id"] or cues["session_id"] != session_id
                    or prescription["decision_id"] != decision["decision_id"]
                    or prescription["session_id"] != session_id
                    or prescription["payload"].get("drill_id") != cues["payload"].get("drill_id")):
                raise HTTPException(status_code=409, detail="response-to-retest lineage is inconsistent")
            _validate_drill_sql(cur, drill_id=prescription["payload"]["drill_id"],
                                athlete_id=athlete_id, decision=decision, principal=principal)
            baseline = _baseline_measurements_sql(
                cur, baseline_reference=payload["baseline_reference"],
                athlete_id=athlete_id, decision=decision,
            )
            _validate_retest_metric_continuity(
                response_payload=response["payload"],
                retest_values=payload.get("retest_values", {}),
                baseline_measurements=baseline,
            )
            _validate_evidence_sql(cur, payload.get("evidence_refs", []),
                                   athlete_id=athlete_id, decision=decision)
        return decision["decision_id"], session["session_id"]

    if feature_id == "FEAT-038":
        retest = _parent_record_sql(cur, record_id=payload["retest_record_id"],
                                    feature_id="FEAT-037", athlete_id=athlete_id, principal=principal)
        if not retest["session_id"] or not retest["decision_id"]:
            raise HTTPException(status_code=409, detail="retest record has incomplete decision/session lineage")
        session, decision = _session_context_sql(cur, session_id=retest["session_id"],
                                                 athlete_id=athlete_id, principal=principal)
        if decision["decision_id"] != retest["decision_id"]:
            raise HTTPException(status_code=409, detail="retest record decision/session lineage is inconsistent")
        baseline = _baseline_measurements_sql(cur, baseline_reference=retest["payload"]["baseline_reference"],
                                               athlete_id=athlete_id, decision=decision)
        if payload.get("baseline") != baseline or payload.get("current") != retest["payload"].get("retest_values"):
            raise HTTPException(status_code=409, detail="comparison values must match the referenced baseline and retest")
        return decision["decision_id"], session["session_id"]

    if feature_id == "FEAT-039":
        comparison = _parent_record_sql(cur, record_id=payload["comparison_record_id"],
                                        feature_id="FEAT-038", athlete_id=athlete_id, principal=principal)
        if not comparison["session_id"] or not comparison["decision_id"]:
            raise HTTPException(status_code=409, detail="comparison record has incomplete decision/session lineage")
        session, decision = _session_context_sql(cur, session_id=comparison["session_id"],
                                                 athlete_id=athlete_id, principal=principal)
        if decision["decision_id"] != comparison["decision_id"]:
            raise HTTPException(status_code=409, detail="comparison record decision/session lineage is inconsistent")
        current = comparison["payload"].get("current", {})
        state = payload.get("state", {})
        if not state or any(state.get(key) != value for key, value in current.items()):
            raise HTTPException(status_code=409, detail="progress state must preserve the referenced comparison values")
        _validate_evidence_sql(cur, payload.get("evidence_refs", []), athlete_id=athlete_id, decision=decision)
        return decision["decision_id"], session["session_id"]

    if feature_id == "FEAT-040":
        progress = _parent_record_sql(cur, record_id=payload["progress_record_id"],
                                      feature_id="FEAT-039", athlete_id=athlete_id, principal=principal)
        if not progress["session_id"] or not progress["decision_id"]:
            raise HTTPException(status_code=409, detail="progress record has incomplete decision/session lineage")
        session, decision = _session_context_sql(cur, session_id=progress["session_id"],
                                                 athlete_id=athlete_id, principal=principal)
        if session_id != session["session_id"] or decision["decision_id"] != progress["decision_id"]:
            raise HTTPException(status_code=409, detail="next-decision trigger must match the referenced progress session")
        _validate_evidence_sql(cur, payload.get("required_evidence", []),
                               athlete_id=athlete_id, decision=decision)
        return decision["decision_id"], session["session_id"]

    raise HTTPException(status_code=400, detail="unsupported Coach workflow feature")


def _validate_lineage_memory(*, feature_id: str, athlete_id: str,
                             principal: Any, payload: Dict[str, Any],
                             decision_id: str | None, session_id: str | None) -> tuple[str, str | None]:
    if feature_id == "FEAT-033":
        if not decision_id:
            raise HTTPException(status_code=400, detail="decision_id is required")
        decision = _decision_context_memory(decision_id=decision_id, athlete_id=athlete_id, principal=principal)
        _validate_drill_memory(drill_id=payload["drill_id"], athlete_id=athlete_id,
                               decision=decision, principal=principal)
        _validate_evidence_memory(payload.get("evidence_refs", []), athlete_id=athlete_id, decision=decision)
        return decision["decision_id"], None

    if feature_id == "FEAT-034":
        if not decision_id or not session_id:
            raise HTTPException(status_code=400, detail="decision_id and session_id are required")
        decision = _decision_context_memory(decision_id=decision_id, athlete_id=athlete_id, principal=principal)
        session, session_decision = _session_context_memory(session_id=session_id, athlete_id=athlete_id, principal=principal)
        if session_decision["decision_id"] != decision["decision_id"]:
            raise HTTPException(status_code=409, detail="session does not belong to the supplied decision")
        selection = _parent_record_memory(record_id=payload["selection_record_id"],
                                          feature_id="FEAT-033", athlete_id=athlete_id, principal=principal)
        if (selection["decision_id"] != decision["decision_id"] or selection["session_id"] is not None
                or selection["payload"].get("drill_id") != payload["drill_id"]):
            raise HTTPException(status_code=409, detail="prescription must reference the selected drill for this decision")
        _validate_drill_memory(drill_id=payload["drill_id"], athlete_id=athlete_id,
                               decision=decision, principal=principal)
        return decision["decision_id"], session["session_id"]

    if feature_id in {"FEAT-035", "FEAT-036", "FEAT-037"}:
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        session, decision = _session_context_memory(session_id=session_id, athlete_id=athlete_id, principal=principal)
        if feature_id == "FEAT-035":
            prescription = _parent_record_memory(record_id=payload["prescription_record_id"],
                                                 feature_id="FEAT-034", athlete_id=athlete_id, principal=principal)
            if (prescription["decision_id"] != decision["decision_id"]
                    or prescription["session_id"] != session_id
                    or prescription["payload"].get("drill_id") != payload["drill_id"]):
                raise HTTPException(status_code=409, detail="execution cues must reference the matching prescription and drill")
            _validate_drill_memory(drill_id=payload["drill_id"], athlete_id=athlete_id,
                                   decision=decision, principal=principal)
        elif feature_id == "FEAT-036":
            cues = _parent_record_memory(record_id=payload["cue_record_id"],
                                         feature_id="FEAT-035", athlete_id=athlete_id, principal=principal)
            if cues["decision_id"] != decision["decision_id"] or cues["session_id"] != session_id:
                raise HTTPException(status_code=409, detail="training response must reference execution cues from this session")
            prescription = _parent_record_memory(
                record_id=cues["payload"].get("prescription_record_id", ""),
                feature_id="FEAT-034", athlete_id=athlete_id, principal=principal,
            )
            if (prescription["decision_id"] != decision["decision_id"]
                    or prescription["session_id"] != session_id
                    or prescription["payload"].get("drill_id") != cues["payload"].get("drill_id")):
                raise HTTPException(status_code=409, detail="execution cue prescription lineage is inconsistent")
            _validate_drill_memory(drill_id=prescription["payload"]["drill_id"],
                                   athlete_id=athlete_id, decision=decision, principal=principal)
        else:
            response = _parent_record_memory(record_id=payload["response_record_id"],
                                             feature_id="FEAT-036", athlete_id=athlete_id, principal=principal)
            if response["decision_id"] != decision["decision_id"] or response["session_id"] != session_id:
                raise HTTPException(status_code=409, detail="retest must reference a response from this session")
            cues = _parent_record_memory(
                record_id=response["payload"].get("cue_record_id", ""),
                feature_id="FEAT-035", athlete_id=athlete_id, principal=principal,
            )
            prescription = _parent_record_memory(
                record_id=cues["payload"].get("prescription_record_id", ""),
                feature_id="FEAT-034", athlete_id=athlete_id, principal=principal,
            )
            if (cues["decision_id"] != decision["decision_id"] or cues["session_id"] != session_id
                    or prescription["decision_id"] != decision["decision_id"]
                    or prescription["session_id"] != session_id
                    or prescription["payload"].get("drill_id") != cues["payload"].get("drill_id")):
                raise HTTPException(status_code=409, detail="response-to-retest lineage is inconsistent")
            _validate_drill_memory(drill_id=prescription["payload"]["drill_id"],
                                   athlete_id=athlete_id, decision=decision, principal=principal)
            baseline = _baseline_measurements_memory(
                baseline_reference=payload["baseline_reference"],
                athlete_id=athlete_id, decision=decision,
            )
            _validate_retest_metric_continuity(
                response_payload=response["payload"],
                retest_values=payload.get("retest_values", {}),
                baseline_measurements=baseline,
            )
            _validate_evidence_memory(payload.get("evidence_refs", []),
                                      athlete_id=athlete_id, decision=decision)
        return decision["decision_id"], session["session_id"]

    if feature_id == "FEAT-038":
        retest = _parent_record_memory(record_id=payload["retest_record_id"],
                                       feature_id="FEAT-037", athlete_id=athlete_id, principal=principal)
        if not retest.get("session_id") or not retest.get("decision_id"):
            raise HTTPException(status_code=409, detail="retest record has incomplete decision/session lineage")
        session, decision = _session_context_memory(session_id=retest["session_id"],
                                                    athlete_id=athlete_id, principal=principal)
        if decision["decision_id"] != retest["decision_id"]:
            raise HTTPException(status_code=409, detail="retest record decision/session lineage is inconsistent")
        baseline = _baseline_measurements_memory(baseline_reference=retest["payload"]["baseline_reference"],
                                                 athlete_id=athlete_id, decision=decision)
        if payload.get("baseline") != baseline or payload.get("current") != retest["payload"].get("retest_values"):
            raise HTTPException(status_code=409, detail="comparison values must match the referenced baseline and retest")
        return decision["decision_id"], session["session_id"]

    if feature_id == "FEAT-039":
        comparison = _parent_record_memory(record_id=payload["comparison_record_id"],
                                           feature_id="FEAT-038", athlete_id=athlete_id, principal=principal)
        if not comparison.get("session_id") or not comparison.get("decision_id"):
            raise HTTPException(status_code=409, detail="comparison record has incomplete decision/session lineage")
        session, decision = _session_context_memory(session_id=comparison["session_id"],
                                                    athlete_id=athlete_id, principal=principal)
        if decision["decision_id"] != comparison["decision_id"]:
            raise HTTPException(status_code=409, detail="comparison record decision/session lineage is inconsistent")
        current = comparison["payload"].get("current", {})
        state = payload.get("state", {})
        if not state or any(state.get(key) != value for key, value in current.items()):
            raise HTTPException(status_code=409, detail="progress state must preserve the referenced comparison values")
        _validate_evidence_memory(payload.get("evidence_refs", []), athlete_id=athlete_id, decision=decision)
        return decision["decision_id"], session["session_id"]

    if feature_id == "FEAT-040":
        progress = _parent_record_memory(record_id=payload["progress_record_id"],
                                         feature_id="FEAT-039", athlete_id=athlete_id, principal=principal)
        if not progress.get("session_id") or not progress.get("decision_id"):
            raise HTTPException(status_code=409, detail="progress record has incomplete decision/session lineage")
        session, decision = _session_context_memory(session_id=progress["session_id"],
                                                    athlete_id=athlete_id, principal=principal)
        if session_id != session["session_id"] or decision["decision_id"] != progress["decision_id"]:
            raise HTTPException(status_code=409, detail="next-decision trigger must match the referenced progress session")
        _validate_evidence_memory(payload.get("required_evidence", []), athlete_id=athlete_id, decision=decision)
        return decision["decision_id"], session["session_id"]

    raise HTTPException(status_code=400, detail="unsupported Coach workflow feature")


class DecisionDrillRequest(BaseModel):
    athlete_id: str
    decision_id: str
    drill_id: str
    rationale: str
    evidence_refs: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class DrillPrescriptionRequest(BaseModel):
    athlete_id: str
    decision_id: str
    session_id: str
    selection_record_id: str
    drill_id: str
    objective: str
    dosage: Dict[str, Any]
    constraints: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class ExecutionCueRequest(BaseModel):
    athlete_id: str
    session_id: str
    prescription_record_id: str
    drill_id: str
    cues: List[str] = Field(min_length=1)
    checklist: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class ResponseRequest(BaseModel):
    athlete_id: str
    session_id: str
    cue_record_id: str
    response: Dict[str, Any]
    kpi_values: Dict[str, Any]
    coach_final_authority: bool = True


class RetestRequest(BaseModel):
    athlete_id: str
    session_id: str
    response_record_id: str
    baseline_reference: str
    retest_values: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class ComparisonRequest(BaseModel):
    athlete_id: str
    baseline: Dict[str, Any]
    current: Dict[str, Any]
    comparison_method: str
    retest_record_id: str
    coach_final_authority: bool = True


class ProgressRequest(BaseModel):
    athlete_id: str
    state: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)
    comparison_record_id: str
    coach_final_authority: bool = True


class NextDecisionRequest(BaseModel):
    athlete_id: str
    session_id: str
    progress_record_id: str
    trigger_type: str
    trigger_reason: str
    required_evidence: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


def _headers(
    authorization: str | None, actor_id: str | None, role: str | None,
    tenant_id: str | None, owner: str | None, athlete_id: str,
):
    return _coach_for_athlete(athlete_id, authorization, actor_id, role, tenant_id, owner)


@router.post("/feat-033/decision-drill", status_code=status.HTTP_201_CREATED)
def select_decision_drill(
    req: DecisionDrillRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    if not req.rationale.strip() or not req.drill_id.strip():
        raise HTTPException(400, "drill_id and rationale are required")
    return _save("FEAT-033", req.athlete_id, req.model_dump(), principal, req.decision_id)


@router.post("/feat-034/drill-prescription", status_code=status.HTTP_201_CREATED)
def prescribe_drill(
    req: DrillPrescriptionRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    d = req.dosage
    if not d or any(k not in d for k in ("sets", "reps")):
        raise HTTPException(400, "dosage requires sets and reps")
    if not isinstance(d["sets"], int) or d["sets"] <= 0 or not isinstance(d["reps"], int) or d["reps"] <= 0:
        raise HTTPException(400, "sets and reps must be positive integers")
    return _save("FEAT-034", req.athlete_id, req.model_dump(), principal, req.decision_id, req.session_id)


@router.post("/feat-035/execution-cues", status_code=status.HTTP_201_CREATED)
def record_execution_cues(
    req: ExecutionCueRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    if any(not item.strip() for item in req.cues + req.checklist):
        raise HTTPException(400, "cues and checklist items must be non-empty")
    return _save("FEAT-035", req.athlete_id, req.model_dump(), principal, session_id=req.session_id)


@router.post("/feat-036/training-response", status_code=status.HTTP_201_CREATED)
def capture_training_response(
    req: ResponseRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    if not req.response or not req.kpi_values:
        raise HTTPException(400, "response and kpi_values are required")
    return _save("FEAT-036", req.athlete_id, req.model_dump(), principal, session_id=req.session_id)


@router.post("/feat-037/retest", status_code=status.HTTP_201_CREATED)
def capture_retest(
    req: RetestRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    if not req.baseline_reference.strip() or not req.retest_values:
        raise HTTPException(400, "baseline_reference and retest_values are required")
    return _save("FEAT-037", req.athlete_id, req.model_dump(), principal, session_id=req.session_id)


@router.post("/feat-038/before-after", status_code=status.HTTP_201_CREATED)
def compare_before_after(
    req: ComparisonRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    if not req.baseline or not req.current or not req.comparison_method.strip():
        raise HTTPException(400, "baseline, current and comparison_method are required")
    return _save("FEAT-038", req.athlete_id, req.model_dump(), principal)


@router.post("/feat-039/progress-state", status_code=status.HTTP_201_CREATED)
def update_progress_state(
    req: ProgressRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    if not req.state:
        raise HTTPException(400, "state is required")
    return _save("FEAT-039", req.athlete_id, req.model_dump(), principal)


@router.post("/feat-040/next-decision-trigger", status_code=status.HTTP_201_CREATED)
def create_next_decision_trigger(
    req: NextDecisionRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    if not req.trigger_type.strip() or not req.trigger_reason.strip():
        raise HTTPException(400, "trigger_type and trigger_reason are required")
    return _save("FEAT-040", req.athlete_id, req.model_dump(), principal, session_id=req.session_id)


@router.get("/athletes/{athlete_id}")
def get_training_workflow(
    athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, athlete_id)
    return {
        "athlete_id": athlete_id,
        "features": {
            feature: _list(feature, athlete_id, principal.tenant_id, principal.actor_id)
            for feature in (
                "FEAT-033", "FEAT-034", "FEAT-035", "FEAT-036",
                "FEAT-037", "FEAT-038", "FEAT-039", "FEAT-040",
            )
        },
        "coach_final_authority": True,
        "execution_authorized": False,
    }
