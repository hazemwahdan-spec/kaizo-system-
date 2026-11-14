"""Coach-scoped, PostgreSQL-only evidence and audit service.

This additive service is intentionally not mounted as an API router. It accepts
only a verified OIDC Coach Principal, derives actor/tenant from that Principal,
and requires the existing primary ownership row for every athlete operation.
Legacy unscoped FEAT-047..050 and FEAT-052..055 routes remain fail-closed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

import persistence
from productization.identity import principal_has_permission


class CoachEvidenceAuthorizationError(PermissionError):
    """The verified Coach Principal does not own or may not access the resource."""


class CoachEvidenceConflict(ValueError):
    """The requested evidence/lifecycle/link operation conflicts with current state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_principal(principal: Any) -> tuple[str, str]:
    if (
        getattr(principal, "verified", False) is not True
        or getattr(principal, "source", None) != "oidc_jwt"
        or getattr(principal, "role", None) != "coach"
        or not principal_has_permission(principal, "product")
    ):
        raise CoachEvidenceAuthorizationError("verified OIDC Coach with Product permission is required")
    actor = str(getattr(principal, "actor_id", "") or "").strip()
    tenant = str(getattr(principal, "tenant_id", "") or "").strip()
    if not actor or not tenant:
        raise CoachEvidenceAuthorizationError("verified Coach actor and tenant claims are required")
    if not persistence.is_postgres_enabled():
        raise RuntimeError("Coach evidence and audit require durable PostgreSQL persistence")
    return tenant, actor


def ensure_schema() -> None:
    """Create additive, tenant/Coach/athlete-scoped tables on a disposable DB."""
    if not persistence.is_postgres_enabled():
        raise RuntimeError("Coach evidence schema requires PostgreSQL")
    ddl = """
    CREATE TABLE IF NOT EXISTS kaizo_coach_scoped_knowledge (
        tenant_id TEXT NOT NULL,
        coach_actor_id TEXT NOT NULL,
        athlete_id TEXT NOT NULL,
        knowledge_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        source_version TEXT NOT NULL,
        evidence_status TEXT NOT NULL CHECK (evidence_status IN ('UNVERIFIED','VERIFIED','CONFLICTED','STALE','REJECTED')),
        provenance_note TEXT NOT NULL,
        evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
        lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('DRAFT','REVIEW','APPROVED','RETIRED','REJECTED')),
        version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, coach_actor_id, athlete_id, knowledge_id),
        FOREIGN KEY (tenant_id, coach_actor_id, athlete_id)
          REFERENCES kaizo_coach_athlete_ownership (tenant_id, coach_actor_id, athlete_id)
          ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_coach_scoped_knowledge_retrieval
      ON kaizo_coach_scoped_knowledge (tenant_id, coach_actor_id, athlete_id, lifecycle_status, evidence_status);
    CREATE TABLE IF NOT EXISTS kaizo_coach_scoped_knowledge_links (
        link_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        coach_actor_id TEXT NOT NULL,
        athlete_id TEXT NOT NULL,
        knowledge_id TEXT NOT NULL,
        unit_type TEXT NOT NULL CHECK (unit_type = 'TRAINING_SESSION'),
        unit_id TEXT NOT NULL,
        link_type TEXT NOT NULL,
        evidence_refs JSONB NOT NULL,
        linked_at TEXT NOT NULL,
        UNIQUE (tenant_id, coach_actor_id, athlete_id, knowledge_id, unit_type, unit_id, link_type),
        FOREIGN KEY (tenant_id, coach_actor_id, athlete_id, knowledge_id)
          REFERENCES kaizo_coach_scoped_knowledge (tenant_id, coach_actor_id, athlete_id, knowledge_id)
          ON DELETE RESTRICT
    );
    CREATE TABLE IF NOT EXISTS kaizo_coach_scoped_actor_trace (
        trace_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        coach_actor_id TEXT NOT NULL,
        athlete_id TEXT NOT NULL,
        action TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
        correlation_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (tenant_id, coach_actor_id, athlete_id)
          REFERENCES kaizo_coach_athlete_ownership (tenant_id, coach_actor_id, athlete_id)
          ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_coach_scoped_actor_trace
      ON kaizo_coach_scoped_actor_trace (tenant_id, coach_actor_id, athlete_id, occurred_at DESC);
    CREATE TABLE IF NOT EXISTS kaizo_coach_scoped_governance (
        governance_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        coach_actor_id TEXT NOT NULL,
        athlete_id TEXT NOT NULL,
        resource_type TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        governance_status TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
        updated_at TEXT NOT NULL,
        UNIQUE (tenant_id, coach_actor_id, athlete_id, resource_type, resource_id),
        FOREIGN KEY (tenant_id, coach_actor_id, athlete_id)
          REFERENCES kaizo_coach_athlete_ownership (tenant_id, coach_actor_id, athlete_id)
          ON DELETE RESTRICT
    );
    """
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()


def _lock_primary_owner(cur: Any, *, tenant_id: str, coach_actor_id: str, athlete_id: str) -> None:
    cur.execute(
        """SELECT athlete_id FROM kaizo_coach_athlete_ownership
           WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
           FOR KEY SHARE""",
        (tenant_id, coach_actor_id, athlete_id),
    )
    if cur.fetchone() is None:
        raise CoachEvidenceAuthorizationError("athlete is outside the authenticated Coach primary-ownership scope")


def _audit(principal: Any, tenant_id: str, action: str, old_value: Any, new_value: Any, timestamp: str) -> None:
    persistence.append_tenant_audit(
        tenant_id=tenant_id, timestamp=timestamp, who=principal.actor_id,
        action=action, old_value=old_value, new_value=new_value,
        why="Coach-scoped evidence operation authorized by verified OIDC Principal and primary ownership.",
    )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, (list, tuple)):
        return []
    result = [str(item).strip() for item in value]
    return result if all(result) else []


def _verified_evidence_ids(cur: Any, evidence_refs: Iterable[str], athlete_id: str) -> set[str]:
    """Lock and resolve verified evidence for this exact athlete in the current transaction."""
    refs = _string_list(evidence_refs)
    if not refs or len(refs) != len(set(refs)):
        return set()
    cur.execute(
        """SELECT evidence_id FROM kaizo_evidence_records
           WHERE evidence_id = ANY(%s) AND subject_type='athlete'
             AND subject_id=%s AND status='VERIFIED'
           FOR SHARE""",
        (refs, athlete_id),
    )
    return {str(row[0]) for row in cur.fetchall()}


def record_provenance(
    *, principal: Any, athlete_id: str, knowledge_id: str, source_type: str,
    source_ref: str, source_version: str, provenance_note: str,
    evidence_refs: Iterable[str],
) -> dict[str, Any]:
    tenant, actor = _require_principal(principal)
    values = [str(x).strip() for x in evidence_refs]
    if not all(str(x).strip() for x in (athlete_id, knowledge_id, source_type, source_ref, source_version, provenance_note)) or not values or any(not x for x in values):
        raise ValueError("athlete, knowledge, source, version, note and evidence references are required")
    timestamp = _now()
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            _lock_primary_owner(cur, tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete_id)
            verified_ids = _verified_evidence_ids(cur, values, athlete_id)
            evidence_status = "VERIFIED" if len(verified_ids) == len(values) == len(set(values)) else "UNVERIFIED"
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_coach_scoped_knowledge
                   WHERE tenant_id=%s AND source_type=%s AND source_ref=%s
                     AND source_version<>%s AND lifecycle_status NOT IN ('RETIRED','REJECTED')""",
                (tenant, source_type, source_ref, source_version),
            )
            if int(cur.fetchone()[0]) > 0:
                evidence_status = "CONFLICTED"
            cur.execute(
                """INSERT INTO kaizo_coach_scoped_knowledge
                   (tenant_id,coach_actor_id,athlete_id,knowledge_id,source_type,source_ref,
                    source_version,evidence_status,provenance_note,evidence_refs,lifecycle_status,
                    version,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'DRAFT',1,%s,%s)""",
                (tenant, actor, athlete_id, knowledge_id, source_type, source_ref, source_version,
                 evidence_status, provenance_note, json.dumps(values), timestamp, timestamp),
            )
            record = {
                "knowledge_id": knowledge_id, "tenant_id": tenant, "coach_actor_id": actor,
                "athlete_id": athlete_id, "source_type": source_type, "source_ref": source_ref,
                "source_version": source_version, "evidence_status": evidence_status,
                "provenance_note": provenance_note, "evidence_refs": values,
                "lifecycle_status": "DRAFT", "version": 1,
            }
            _audit(principal, tenant, "COACH_FEAT047_PROVENANCE_RECORDED", None, record, timestamp)
    return record


def change_lifecycle(
    *, principal: Any, athlete_id: str, knowledge_id: str,
    target_status: str, expected_version: int,
) -> dict[str, Any]:
    tenant, actor = _require_principal(principal)
    allowed = {
        "DRAFT": {"REVIEW", "REJECTED"},
        "REVIEW": {"DRAFT", "APPROVED", "REJECTED"},
        "APPROVED": {"RETIRED"},
        "RETIRED": set(), "REJECTED": set(),
    }
    timestamp = _now()
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            _lock_primary_owner(cur, tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete_id)
            cur.execute(
                """SELECT lifecycle_status,evidence_status,version,evidence_refs FROM kaizo_coach_scoped_knowledge
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s AND knowledge_id=%s
                   FOR UPDATE""",
                (tenant, actor, athlete_id, knowledge_id),
            )
            row = cur.fetchone()
            if row is None:
                raise CoachEvidenceConflict("knowledge record not found in Coach scope")
            old_status, evidence_status, version = str(row[0]), str(row[1]), int(row[2])
            if version != expected_version:
                raise CoachEvidenceConflict("knowledge version changed; reload before retry")
            if target_status not in allowed.get(old_status, set()):
                raise CoachEvidenceConflict("invalid knowledge lifecycle transition")
            if target_status == "APPROVED":
                provenance_refs = _string_list(row[3])
                verified_ids = _verified_evidence_ids(cur, provenance_refs, athlete_id)
                if (evidence_status != "VERIFIED" or not provenance_refs
                        or len(provenance_refs) != len(set(provenance_refs))
                        or len(verified_ids) != len(provenance_refs)):
                    raise CoachEvidenceConflict("all provenance evidence must remain VERIFIED for this athlete before approval")
            cur.execute(
                """UPDATE kaizo_coach_scoped_knowledge
                   SET lifecycle_status=%s,version=version+1,updated_at=%s
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s AND knowledge_id=%s
                   RETURNING lifecycle_status,version""",
                (target_status, timestamp, tenant, actor, athlete_id, knowledge_id),
            )
            new_status, new_version = cur.fetchone()
            old_value = {"knowledge_id": knowledge_id, "lifecycle_status": old_status, "version": version}
            new_value = {"knowledge_id": knowledge_id, "lifecycle_status": new_status, "version": int(new_version)}
            _audit(principal, tenant, "COACH_FEAT048_LIFECYCLE_CHANGED", old_value, new_value, timestamp)
    return new_value


def retrieve_knowledge(*, principal: Any, athlete_id: str, query: str, limit: int = 20) -> list[dict[str, Any]]:
    tenant, actor = _require_principal(principal)
    q = str(query or "").strip()
    if not q:
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 50))
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            _lock_primary_owner(cur, tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete_id)
            cur.execute(
                """SELECT knowledge_id,source_type,source_ref,source_version,evidence_status,
                          provenance_note,evidence_refs,lifecycle_status,version
                   FROM kaizo_coach_scoped_knowledge
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                     AND lifecycle_status='APPROVED' AND evidence_status='VERIFIED'
                     AND (knowledge_id ILIKE %s OR provenance_note ILIKE %s OR source_ref ILIKE %s)
                   ORDER BY updated_at DESC LIMIT %s
                   FOR SHARE""",
                (tenant, actor, athlete_id, f"%{q}%", f"%{q}%", f"%{q}%", limit),
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                provenance_refs = _string_list(r[6])
                verified_ids = _verified_evidence_ids(cur, provenance_refs, athlete_id)
                if (not provenance_refs or len(provenance_refs) != len(set(provenance_refs))
                        or len(verified_ids) != len(provenance_refs)):
                    continue
                results.append({
                    "knowledge_id": r[0], "source_type": r[1], "source_ref": r[2],
                    "source_version": r[3], "evidence_status": r[4], "provenance_note": r[5],
                    "evidence_refs": r[6], "lifecycle_status": r[7], "version": int(r[8]),
                })
            _audit(principal, tenant, "COACH_FEAT049_KNOWLEDGE_RETRIEVED",
                   None, {"athlete_id": athlete_id, "query": q, "result_count": len(results)}, _now())
    return results


def link_training_session(
    *, principal: Any, athlete_id: str, knowledge_id: str, session_id: str,
    link_type: str, evidence_refs: Iterable[str],
) -> dict[str, Any]:
    tenant, actor = _require_principal(principal)
    refs = [str(x).strip() for x in evidence_refs]
    if not link_type.strip() or not refs or any(not x for x in refs):
        raise ValueError("link_type and evidence references are required")
    timestamp = _now()
    link_id = str(uuid4())
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            _lock_primary_owner(cur, tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete_id)
            cur.execute(
                """SELECT lifecycle_status,evidence_status,evidence_refs FROM kaizo_coach_scoped_knowledge
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s AND knowledge_id=%s
                   FOR SHARE""",
                (tenant, actor, athlete_id, knowledge_id),
            )
            knowledge = cur.fetchone()
            if knowledge is None or knowledge[0] != "APPROVED" or knowledge[1] != "VERIFIED":
                raise CoachEvidenceConflict("approved, verified knowledge is required in the same Coach athlete scope")
            provenance_refs = _string_list(knowledge[2])
            if (not provenance_refs or len(provenance_refs) != len(set(provenance_refs))
                    or len(set(refs)) != len(refs)
                    or not set(refs).issubset(set(provenance_refs))):
                raise CoachEvidenceConflict("linkage evidence must be a unique subset of the knowledge provenance evidence")
            verified_ids = _verified_evidence_ids(cur, provenance_refs, athlete_id)
            if len(verified_ids) != len(provenance_refs):
                raise CoachEvidenceConflict("all knowledge provenance evidence must remain VERIFIED for this athlete")
            cur.execute(
                """SELECT session_id FROM kaizo_training_sessions
                   WHERE session_id=%s AND athlete_id=%s AND created_by=%s
                   FOR SHARE""",
                (session_id, athlete_id, actor),
            )
            if cur.fetchone() is None:
                raise CoachEvidenceAuthorizationError("training session is outside the authenticated Coach athlete scope")
            cur.execute(
                """INSERT INTO kaizo_coach_scoped_knowledge_links
                   (link_id,tenant_id,coach_actor_id,athlete_id,knowledge_id,unit_type,unit_id,
                    link_type,evidence_refs,linked_at)
                   VALUES (%s,%s,%s,%s,%s,'TRAINING_SESSION',%s,%s,%s::jsonb,%s)""",
                (link_id, tenant, actor, athlete_id, knowledge_id, session_id, link_type, json.dumps(refs), timestamp),
            )
            record = {"link_id": link_id, "knowledge_id": knowledge_id, "athlete_id": athlete_id,
                      "unit_type": "TRAINING_SESSION", "unit_id": session_id, "link_type": link_type}
            _audit(principal, tenant, "COACH_FEAT050_KNOWLEDGE_LINKED", None, record, timestamp)
    return record


def record_actor_trace(
    *, principal: Any, athlete_id: str, action: str,
    evidence_refs: Iterable[str] = (), correlation_id: str | None = None,
) -> dict[str, Any]:
    tenant, actor = _require_principal(principal)
    action = str(action or "").strip()
    if not action:
        raise ValueError("action is required")
    refs = [str(x).strip() for x in evidence_refs]
    if any(not x for x in refs):
        raise ValueError("evidence references cannot be empty")
    timestamp = _now()
    trace_id = str(uuid4())
    correlation = str(correlation_id or trace_id).strip()
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            _lock_primary_owner(cur, tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete_id)
            if refs:
                verified_ids = _verified_evidence_ids(cur, refs, athlete_id)
                if len(verified_ids) != len(refs):
                    raise CoachEvidenceConflict("actor trace evidence must be VERIFIED and belong to this athlete")
            cur.execute(
                """INSERT INTO kaizo_coach_scoped_actor_trace
                   (trace_id,tenant_id,coach_actor_id,athlete_id,action,occurred_at,evidence_refs,correlation_id,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                (trace_id, tenant, actor, athlete_id, action, timestamp, json.dumps(refs), correlation, timestamp),
            )
            record = {"trace_id": trace_id, "actor_id": actor, "tenant_id": tenant,
                      "athlete_id": athlete_id, "action": action, "occurred_at": timestamp,
                      "evidence_refs": refs, "correlation_id": correlation}
            _audit(principal, tenant, "COACH_FEAT052_ACTOR_ACTION_TRACED", None, record, timestamp)
    return record


def set_governance(
    *, principal: Any, athlete_id: str, resource_type: str, resource_id: str,
    governance_status: str, metadata: dict[str, Any], expected_version: int | None = None,
) -> dict[str, Any]:
    tenant, actor = _require_principal(principal)
    if not all(str(x).strip() for x in (athlete_id, resource_type, resource_id, governance_status)):
        raise ValueError("athlete, resource type/id and governance status are required")
    allowed_resource_types = {"KNOWLEDGE", "TRAINING_SESSION"}
    if resource_type not in allowed_resource_types:
        raise CoachEvidenceConflict("governance resource_type is not enabled in the scoped service")
    timestamp = _now()
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            _lock_primary_owner(cur, tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete_id)
            if resource_type == "KNOWLEDGE":
                cur.execute(
                    """SELECT 1 FROM kaizo_coach_scoped_knowledge
                       WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s AND knowledge_id=%s
                       FOR SHARE""",
                    (tenant, actor, athlete_id, resource_id),
                )
            else:
                cur.execute(
                    """SELECT 1 FROM kaizo_training_sessions
                       WHERE session_id=%s AND athlete_id=%s AND created_by=%s
                       FOR SHARE""",
                    (resource_id, athlete_id, actor),
                )
            if cur.fetchone() is None:
                raise CoachEvidenceAuthorizationError("governance resource is outside the authenticated Coach athlete scope")
            cur.execute(
                """SELECT governance_id,governance_status,metadata,version
                   FROM kaizo_coach_scoped_governance
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                     AND resource_type=%s AND resource_id=%s FOR UPDATE""",
                (tenant, actor, athlete_id, resource_type, resource_id),
            )
            row = cur.fetchone()
            if row is None:
                if expected_version not in (None, 0):
                    raise CoachEvidenceConflict("governance record does not exist at expected version")
                governance_id, old_value, version = str(uuid4()), None, 1
                cur.execute(
                    """INSERT INTO kaizo_coach_scoped_governance
                       (governance_id,tenant_id,coach_actor_id,athlete_id,resource_type,resource_id,
                        governance_status,metadata,version,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,1,%s)""",
                    (governance_id, tenant, actor, athlete_id, resource_type, resource_id,
                     governance_status, json.dumps(metadata), timestamp),
                )
            else:
                governance_id, old_status, old_metadata, old_version = row
                if expected_version is None or int(old_version) != expected_version:
                    raise CoachEvidenceConflict("governance version changed; reload before retry")
                old_value, version = {"status": old_status, "metadata": old_metadata, "version": int(old_version)}, int(old_version) + 1
                cur.execute(
                    """UPDATE kaizo_coach_scoped_governance
                       SET governance_status=%s,metadata=%s::jsonb,version=%s,updated_at=%s
                       WHERE governance_id=%s""",
                    (governance_status, json.dumps(metadata), version, timestamp, governance_id),
                )
            new_value = {"governance_id": governance_id, "athlete_id": athlete_id,
                         "resource_type": resource_type, "resource_id": resource_id,
                         "governance_status": governance_status, "metadata": metadata, "version": version}
            _audit(principal, tenant, "COACH_FEAT053_GOVERNANCE_CHANGED", old_value, new_value, timestamp)
    return new_value
