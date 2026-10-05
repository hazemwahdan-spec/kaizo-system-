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

CREATE TABLE IF NOT EXISTS kaizo_assessment_evidence_attachments (
    assessment_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    attached_by TEXT NOT NULL,
    attached_at TEXT NOT NULL,
    PRIMARY KEY (assessment_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS kaizo_kpi_definitions (
    kpi_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    target DOUBLE PRECISION,
    direction TEXT NOT NULL,
    defined_by TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_kpi_captures (
    capture_id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL,
    kpi_id TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    captured_by TEXT NOT NULL,
    assessment_id TEXT,
    captured_at TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS kaizo_state_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    snapshot_type TEXT NOT NULL,
    measurements JSONB NOT NULL,
    kpis JSONB NOT NULL,
    captured_by TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_problem_library_selections (
    selection_id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    library_item_id TEXT NOT NULL,
    selected_by TEXT NOT NULL,
    selected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_problem_library_selections (
    selection_id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    library_item_id TEXT NOT NULL,
    selected_by TEXT NOT NULL,
    selected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_evidence_linked_diagnoses (
    diagnosis_id TEXT PRIMARY KEY,
    problem_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    evidence_ids JSONB NOT NULL,
    diagnosis TEXT NOT NULL,
    diagnosed_by TEXT NOT NULL,
    confidence TEXT,
    resolution_state TEXT NOT NULL DEFAULT 'UNRESOLVED',
    diagnosed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_cause_context_framings (
    framing_id TEXT PRIMARY KEY,
    problem_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    cause TEXT NOT NULL,
    context JSONB NOT NULL,
    contributing_factors JSONB NOT NULL,
    framed_by TEXT NOT NULL,
    framed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_problem_statements (
    problem_id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    statement TEXT NOT NULL,
    problem_type TEXT NOT NULL,
    impact TEXT,
    context JSONB NOT NULL,
    structured_fields JSONB NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
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




def upsert_problem_library_selection(selection: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_problem_library_selections
                (selection_id, athlete_id, assessment_id, library_item_id, selected_by, selected_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (selection_id) DO UPDATE SET
                    athlete_id=EXCLUDED.athlete_id,
                    assessment_id=EXCLUDED.assessment_id,
                    library_item_id=EXCLUDED.library_item_id,
                    selected_by=EXCLUDED.selected_by,
                    selected_at=EXCLUDED.selected_at""",
                (selection["selection_id"], selection["athlete_id"], selection["assessment_id"],
                 selection["library_item_id"], selection["selected_by"], selection["selected_at"]))
        conn.commit()


def get_problem_library_selection(selection_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT selection_id, athlete_id, assessment_id, library_item_id, selected_by, selected_at
                   FROM kaizo_problem_library_selections WHERE selection_id=%s""",
                (selection_id,))
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "selection_id": row[0],
        "athlete_id": row[1],
        "assessment_id": row[2],
        "library_item_id": row[3],
        "selected_by": row[4],
        "selected_at": row[5],
    }


def upsert_problem_library_selection(selection: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_problem_library_selections
                (selection_id, athlete_id, assessment_id, library_item_id, selected_by, selected_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (selection_id) DO UPDATE SET
                    athlete_id=EXCLUDED.athlete_id,
                    assessment_id=EXCLUDED.assessment_id,
                    library_item_id=EXCLUDED.library_item_id,
                    selected_by=EXCLUDED.selected_by,
                    selected_at=EXCLUDED.selected_at""",
                (selection["selection_id"], selection["athlete_id"], selection["assessment_id"],
                 selection["library_item_id"], selection["selected_by"], selection["selected_at"]))
        conn.commit()


def get_problem_library_selection(selection_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT selection_id, athlete_id, assessment_id, library_item_id, selected_by, selected_at
                   FROM kaizo_problem_library_selections WHERE selection_id=%s""",
                (selection_id,))
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "selection_id": row[0],
        "athlete_id": row[1],
        "assessment_id": row[2],
        "library_item_id": row[3],
        "selected_by": row[4],
        "selected_at": row[5],
    }


def upsert_evidence_linked_diagnosis(diagnosis: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO kaizo_evidence_linked_diagnoses
                (diagnosis_id, problem_id, athlete_id, assessment_id, evidence_ids, diagnosis, diagnosed_by, confidence, resolution_state, diagnosed_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                ON CONFLICT (diagnosis_id) DO UPDATE SET evidence_ids=EXCLUDED.evidence_ids,
                diagnosis=EXCLUDED.diagnosis, diagnosed_by=EXCLUDED.diagnosed_by,
                confidence=EXCLUDED.confidence, resolution_state=EXCLUDED.resolution_state, diagnosed_at=EXCLUDED.diagnosed_at""",
                (diagnosis["diagnosis_id"], diagnosis["problem_id"], diagnosis["athlete_id"],
                 diagnosis["assessment_id"], json.dumps(diagnosis["evidence_ids"]),
                 diagnosis["diagnosis"], diagnosis["diagnosed_by"], diagnosis["confidence"],
                 diagnosis["resolution_state"], diagnosis["diagnosed_at"]))
        conn.commit()


def list_evidence_linked_diagnoses(problem_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT diagnosis_id, problem_id, athlete_id, assessment_id,
                                  evidence_ids, diagnosis, diagnosed_by, confidence, resolution_state, diagnosed_at
                           FROM kaizo_evidence_linked_diagnoses WHERE problem_id=%s
                           ORDER BY diagnosed_at""", (problem_id,))
            rows=cur.fetchall()
    return [{"diagnosis_id":r[0],"problem_id":r[1],"athlete_id":r[2],"assessment_id":r[3],
             "evidence_ids":r[4],"diagnosis":r[5],"diagnosed_by":r[6],"confidence":r[7],
             "resolution_state":r[8],"diagnosed_at":r[9]} for r in rows]


def upsert_cause_context_framing(framing: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_cause_context_framings
                (framing_id, problem_id, athlete_id, assessment_id, cause, context, contributing_factors, framed_by, framed_at)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                ON CONFLICT (framing_id) DO UPDATE SET
                    cause=EXCLUDED.cause, context=EXCLUDED.context,
                    contributing_factors=EXCLUDED.contributing_factors,
                    framed_by=EXCLUDED.framed_by, framed_at=EXCLUDED.framed_at""",
                (framing["framing_id"], framing["problem_id"], framing["athlete_id"], framing["assessment_id"],
                 framing["cause"], json.dumps(framing["context"]), json.dumps(framing["contributing_factors"]),
                 framing["framed_by"], framing["framed_at"]),
            )
        conn.commit()


def list_cause_context_framings(problem_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT framing_id, problem_id, athlete_id, assessment_id, cause, context,
                          contributing_factors, framed_by, framed_at
                   FROM kaizo_cause_context_framings
                   WHERE problem_id=%s ORDER BY framed_at""",
                (problem_id,),
            )
            rows = cur.fetchall()
    return [
        {"framing_id": r[0], "problem_id": r[1], "athlete_id": r[2], "assessment_id": r[3],
         "cause": r[4], "context": r[5], "contributing_factors": r[6],
         "framed_by": r[7], "framed_at": r[8]}
        for r in rows
    ]


def upsert_problem_statement(problem: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_problem_statements
                (problem_id, athlete_id, assessment_id, statement, problem_type, impact,
                 context, structured_fields, status, created_by, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
                ON CONFLICT (problem_id) DO UPDATE SET
                  statement=EXCLUDED.statement, problem_type=EXCLUDED.problem_type,
                  impact=EXCLUDED.impact, context=EXCLUDED.context,
                  structured_fields=EXCLUDED.structured_fields, status=EXCLUDED.status,
                  updated_at=EXCLUDED.updated_at""",
                (problem["problem_id"],problem["athlete_id"],problem["assessment_id"],
                 problem["statement"],problem["problem_type"],problem.get("impact"),
                 json.dumps(problem.get("context",{})),json.dumps(problem.get("structured_fields",{})),
                 problem["status"],problem["created_by"],problem["created_at"],problem["updated_at"]))
        conn.commit()

def get_problem_statement(problem_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT problem_id, athlete_id, assessment_id, statement, problem_type,
                                  impact, context, structured_fields, status, created_by, created_at, updated_at
                           FROM kaizo_problem_statements WHERE problem_id=%s""",(problem_id,))
            row=cur.fetchone()
    if row is None: return None
    return {"problem_id":row[0],"athlete_id":row[1],"assessment_id":row[2],"statement":row[3],
            "problem_type":row[4],"impact":row[5],"context":row[6],"structured_fields":row[7],
            "status":row[8],"created_by":row[9],"created_at":row[10],"updated_at":row[11]}

def list_problem_statements(athlete_id: Optional[str]=None) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            if athlete_id:
                cur.execute("""SELECT problem_id, athlete_id, assessment_id, statement, problem_type,
                                      impact, context, structured_fields, status, created_by, created_at, updated_at
                               FROM kaizo_problem_statements WHERE athlete_id=%s ORDER BY created_at""",(athlete_id,))
            else:
                cur.execute("""SELECT problem_id, athlete_id, assessment_id, statement, problem_type,
                                      impact, context, structured_fields, status, created_by, created_at, updated_at
                               FROM kaizo_problem_statements ORDER BY created_at""")
            rows=cur.fetchall()
    return [{"problem_id":r[0],"athlete_id":r[1],"assessment_id":r[2],"statement":r[3],
             "problem_type":r[4],"impact":r[5],"context":r[6],"structured_fields":r[7],
             "status":r[8],"created_by":r[9],"created_at":r[10],"updated_at":r[11]} for r in rows]

def upsert_state_snapshot(snapshot: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO kaizo_state_snapshots
                (snapshot_id, athlete_id, assessment_id, snapshot_type, measurements, kpis, captured_by, captured_at, created_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                ON CONFLICT (snapshot_id) DO UPDATE SET snapshot_type=EXCLUDED.snapshot_type,
                measurements=EXCLUDED.measurements, kpis=EXCLUDED.kpis, captured_by=EXCLUDED.captured_by,
                captured_at=EXCLUDED.captured_at""",
                (snapshot["snapshot_id"], snapshot["athlete_id"], snapshot["assessment_id"], snapshot["snapshot_type"],
                 json.dumps(snapshot["measurements"]), json.dumps(snapshot["kpis"]), snapshot["captured_by"],
                 snapshot["captured_at"], snapshot["created_at"]))
        conn.commit()

def get_state_snapshot(snapshot_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled(): return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT snapshot_id, athlete_id, assessment_id, snapshot_type, measurements, kpis, captured_by, captured_at, created_at FROM kaizo_state_snapshots WHERE snapshot_id=%s", (snapshot_id,))
            row=cur.fetchone()
    if row is None: return None
    return {"snapshot_id":row[0],"athlete_id":row[1],"assessment_id":row[2],"snapshot_type":row[3],"measurements":row[4],"kpis":row[5],"captured_by":row[6],"captured_at":row[7],"created_at":row[8]}

def list_state_snapshots(athlete_id: Optional[str] = None) -> list[Dict[str, Any]]:
    if not is_postgres_enabled(): return []
    with connection() as conn:
        with conn.cursor() as cur:
            if athlete_id:
                cur.execute("SELECT snapshot_id, athlete_id, assessment_id, snapshot_type, measurements, kpis, captured_by, captured_at, created_at FROM kaizo_state_snapshots WHERE athlete_id=%s ORDER BY captured_at", (athlete_id,))
            else:
                cur.execute("SELECT snapshot_id, athlete_id, assessment_id, snapshot_type, measurements, kpis, captured_by, captured_at, created_at FROM kaizo_state_snapshots ORDER BY captured_at")
            rows=cur.fetchall()
    return [{"snapshot_id":r[0],"athlete_id":r[1],"assessment_id":r[2],"snapshot_type":r[3],"measurements":r[4],"kpis":r[5],"captured_by":r[6],"captured_at":r[7],"created_at":r[8]} for r in rows]

def upsert_kpi_definition(definition: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kaizo_kpi_definitions
                    (kpi_id, name, metric_name, unit, target, direction, defined_by, status, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (kpi_id) DO UPDATE SET
                    name=EXCLUDED.name, metric_name=EXCLUDED.metric_name, unit=EXCLUDED.unit,
                    target=EXCLUDED.target, direction=EXCLUDED.direction, defined_by=EXCLUDED.defined_by,
                    status=EXCLUDED.status, updated_at=EXCLUDED.updated_at
            """, (definition["kpi_id"],definition["name"],definition["metric_name"],definition["unit"],definition.get("target"),definition["direction"],definition["defined_by"],definition["status"],definition["created_at"],definition["updated_at"]))
        conn.commit()


def get_kpi_definition(kpi_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT kpi_id,name,metric_name,unit,target,direction,defined_by,status,created_at,updated_at FROM kaizo_kpi_definitions WHERE kpi_id=%s", (kpi_id,))
            row=cur.fetchone()
    if row is None:
        return None
    return {"kpi_id":row[0],"name":row[1],"metric_name":row[2],"unit":row[3],"target":row[4],"direction":row[5],"defined_by":row[6],"status":row[7],"created_at":row[8],"updated_at":row[9]}


def upsert_kpi_capture(capture: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kaizo_kpi_captures
                    (capture_id,athlete_id,kpi_id,value,captured_by,assessment_id,captured_at,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (capture_id) DO UPDATE SET value=EXCLUDED.value,captured_by=EXCLUDED.captured_by,assessment_id=EXCLUDED.assessment_id,captured_at=EXCLUDED.captured_at
            """, (capture["capture_id"],capture["athlete_id"],capture["kpi_id"],capture["value"],capture["captured_by"],capture.get("assessment_id"),capture["captured_at"],capture["created_at"]))
        conn.commit()


def get_kpi_capture(capture_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT capture_id,athlete_id,kpi_id,value,captured_by,assessment_id,captured_at,created_at FROM kaizo_kpi_captures WHERE capture_id=%s", (capture_id,))
            row=cur.fetchone()
    if row is None:
        return None
    return {"capture_id":row[0],"athlete_id":row[1],"kpi_id":row[2],"value":row[3],"captured_by":row[4],"assessment_id":row[5],"captured_at":row[6],"created_at":row[7]}


def attach_assessment_evidence(attachment: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kaizo_assessment_evidence_attachments
                    (assessment_id, evidence_id, attached_by, attached_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (assessment_id, evidence_id) DO UPDATE SET
                    attached_by = EXCLUDED.attached_by,
                    attached_at = EXCLUDED.attached_at
                """,
                (
                    attachment["assessment_id"],
                    attachment["evidence_id"],
                    attachment["attached_by"],
                    attachment["attached_at"],
                ),
            )
        conn.commit()


def list_assessment_evidence(assessment_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT assessment_id, evidence_id, attached_by, attached_at
                FROM kaizo_assessment_evidence_attachments
                WHERE assessment_id = %s
                ORDER BY attached_at
                """,
                (assessment_id,),
            )
            rows = cur.fetchall()
    return [
        {
            "assessment_id": row[0],
            "evidence_id": row[1],
            "attached_by": row[2],
            "attached_at": row[3],
        }
        for row in rows
    ]
