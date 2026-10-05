"""KAIZO durable persistence adapter.

Infrastructure boundary only. Core decision logic remains outside this module.
Production durability is enabled explicitly with KAIZO_PERSISTENCE_MODE=postgres
and DATABASE_URL. No credentials are stored in source control.
"""

import json
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kaizo_athletes (
    athlete_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_assessments (
    assessment_id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL,
    template_id TEXT NOT NULL,
    measurements JSONB NOT NULL,
    recorded_by TEXT NOT NULL,
    assessed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    who TEXT NOT NULL,
    action TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    why TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_evidence_records (
    evidence_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    evidence_level TEXT NOT NULL,
    status TEXT NOT NULL,
    source_ref TEXT,
    claim TEXT NOT NULL,
    observed_value JSONB,
    verified_by TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS kaizo_digital_twin_state (
    entity_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    state JSONB NOT NULL,
    source_event TEXT NOT NULL,
    case_id TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_knowledge_repository (
    item_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class PersistenceConfigurationError(RuntimeError):
    pass


def mode() -> str:
    return os.getenv("KAIZO_PERSISTENCE_MODE", "memory").strip().lower()


def is_postgres_enabled() -> bool:
    return mode() == "postgres"


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise PersistenceConfigurationError(
            "KAIZO_PERSISTENCE_MODE=postgres requires DATABASE_URL"
        )
    if psycopg is None:
        raise PersistenceConfigurationError(
            "PostgreSQL persistence requires psycopg"
        )
    return value


@contextmanager
def connection() -> Iterator[Any]:
    with psycopg.connect(_database_url()) as conn:
        yield conn


def initialize() -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


def upsert_athlete(athlete: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kaizo_athletes
                    (athlete_id, display_name, status, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (athlete_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    status = EXCLUDED.status,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    athlete["athlete_id"], athlete["display_name"], athlete["status"],
                    json.dumps(athlete.get("metadata", {})),
                    athlete["created_at"], athlete["updated_at"],
                ),
            )
        conn.commit()


def get_athlete(athlete_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT athlete_id, display_name, status, metadata, created_at, updated_at
                FROM kaizo_athletes WHERE athlete_id = %s
                """,
                (athlete_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "athlete_id": row[0], "display_name": row[1], "status": row[2],
        "metadata": row[3], "created_at": row[4], "updated_at": row[5],
    }


def append_audit(
    *,
    timestamp: str,
    who: str,
    action: str,
    old_value: Any,
    new_value: Any,
    why: str,
) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kaizo_audit_logs
                    (timestamp, who, action, old_value, new_value, why)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    timestamp,
                    who,
                    action,
                    json.dumps(old_value),
                    json.dumps(new_value),
                    why,
                ),
            )
        conn.commit()


def list_audit_logs() -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, who, action, old_value, new_value, why
                FROM kaizo_audit_logs
                ORDER BY id
                """
            )
            rows = cur.fetchall()
    return [
        {
            "timestamp": row[0],
            "who": row[1],
            "action": row[2],
            "old_value": row[3],
            "new_value": row[4],
            "why": row[5],
        }
        for row in rows
    ]


def upsert_digital_twin(state: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kaizo_digital_twin_state
                    (entity_id, version, state, source_event, case_id, updated_at)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE SET
                    version = EXCLUDED.version,
                    state = EXCLUDED.state,
                    source_event = EXCLUDED.source_event,
                    case_id = EXCLUDED.case_id,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    state["entity_id"],
                    state["version"],
                    json.dumps(state["state"]),
                    state["source_event"],
                    state["case_id"],
                    state["updated_at"],
                ),
            )
        conn.commit()


def get_digital_twin(entity_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT entity_id, version, state, source_event, case_id, updated_at
                FROM kaizo_digital_twin_state
                WHERE entity_id = %s
                """,
                (entity_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "entity_id": row[0],
        "version": row[1],
        "state": row[2],
        "source_event": row[3],
        "case_id": row[4],
        "updated_at": row[5],
    }


def upsert_knowledge(item_id: str, payload: Dict[str, Any], updated_at: str) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kaizo_knowledge_repository (item_id, payload, updated_at)
                VALUES (%s, %s::jsonb, %s)
                ON CONFLICT (item_id) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                """,
                (item_id, json.dumps(payload), updated_at),
            )
        conn.commit()


def load_knowledge() -> Dict[str, Any]:
    if not is_postgres_enabled():
        return {}
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT item_id, payload FROM kaizo_knowledge_repository ORDER BY item_id"
            )
            rows = cur.fetchall()
    return {row[0]: row[1] for row in rows}


def upsert_assessment(assessment: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kaizo_assessments
                    (assessment_id, athlete_id, template_id, measurements, recorded_by, assessed_at, created_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (assessment_id) DO UPDATE SET
                    measurements = EXCLUDED.measurements,
                    recorded_by = EXCLUDED.recorded_by,
                    assessed_at = EXCLUDED.assessed_at
                """,
                (
                    assessment["assessment_id"],
                    assessment["athlete_id"],
                    assessment["template_id"],
                    json.dumps(assessment.get("measurements", {})),
                    assessment["recorded_by"],
                    assessment["assessed_at"],
                    assessment["created_at"],
                ),
            )
        conn.commit()


def get_assessment(assessment_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT assessment_id, athlete_id, template_id, measurements,
                       recorded_by, assessed_at, created_at
                FROM kaizo_assessments
                WHERE assessment_id = %s
                """,
                (assessment_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "assessment_id": row[0],
        "athlete_id": row[1],
        "template_id": row[2],
        "measurements": row[3],
        "recorded_by": row[4],
        "assessed_at": row[5],
        "created_at": row[6],
    }


def upsert_evidence(record: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kaizo_evidence_records
                    (evidence_id, subject_type, subject_id, evidence_level, status,
                     source_ref, claim, observed_value, verified_by, verified_at, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                ON CONFLICT (evidence_id) DO UPDATE SET
                    evidence_level=EXCLUDED.evidence_level,
                    status=EXCLUDED.status,
                    source_ref=EXCLUDED.source_ref,
                    claim=EXCLUDED.claim,
                    observed_value=EXCLUDED.observed_value,
                    verified_by=EXCLUDED.verified_by,
                    verified_at=EXCLUDED.verified_at,
                    notes=EXCLUDED.notes
                """,
                (
                    record["evidence_id"], record["subject_type"], record["subject_id"],
                    record["evidence_level"], record["status"], record.get("source_ref"),
                    record["claim"], json.dumps(record.get("observed_value")),
                    record["verified_by"], record["verified_at"], record.get("notes"),
                ),
            )
        conn.commit()


def get_evidence(evidence_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT evidence_id, subject_type, subject_id, evidence_level, status,
                          source_ref, claim, observed_value, verified_by, verified_at, notes
                   FROM kaizo_evidence_records WHERE evidence_id=%s""",
                (evidence_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "evidence_id": row[0], "subject_type": row[1], "subject_id": row[2],
        "evidence_level": row[3], "status": row[4], "source_ref": row[5],
        "claim": row[6], "observed_value": row[7], "verified_by": row[8],
        "verified_at": row[9], "notes": row[10],
    }


def list_evidence(subject_id: Optional[str] = None) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            if subject_id:
                cur.execute(
                    """SELECT evidence_id, subject_type, subject_id, evidence_level, status,
                              source_ref, claim, observed_value, verified_by, verified_at, notes
                       FROM kaizo_evidence_records WHERE subject_id=%s ORDER BY verified_at""",
                    (subject_id,),
                )
            else:
                cur.execute(
                    """SELECT evidence_id, subject_type, subject_id, evidence_level, status,
                              source_ref, claim, observed_value, verified_by, verified_at, notes
                       FROM kaizo_evidence_records ORDER BY verified_at"""
                )
            rows = cur.fetchall()
    return [
        {
            "evidence_id": r[0], "subject_type": r[1], "subject_id": r[2],
            "evidence_level": r[3], "status": r[4], "source_ref": r[5],
            "claim": r[6], "observed_value": r[7], "verified_by": r[8],
            "verified_at": r[9], "notes": r[10],
        } for r in rows
    ]
