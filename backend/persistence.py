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


ALTER TABLE kaizo_evidence_linked_diagnoses
    ADD COLUMN IF NOT EXISTS resolution_state TEXT NOT NULL DEFAULT 'UNRESOLVED';
CREATE TABLE IF NOT EXISTS kaizo_decision_candidates (
    candidate_id TEXT PRIMARY KEY,
    diagnosis_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    title TEXT NOT NULL,
    rationale TEXT NOT NULL,
    source_diagnosis TEXT NOT NULL,
    status TEXT NOT NULL,
    generated_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_decision_rationales (
    rationale_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    diagnosis_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_ids JSONB NOT NULL,
    recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_decision_comparisons (
    comparison_id TEXT PRIMARY KEY,
    diagnosis_id TEXT NOT NULL,
    candidate_ids JSONB NOT NULL,
    alternatives JSONB NOT NULL,
    comparison_status TEXT NOT NULL,
    compared_by TEXT NOT NULL,
    compared_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_coach_decision_reviews (
    review_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    diagnosis_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    coach_id TEXT NOT NULL,
    override_reason TEXT,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_decision_records (
    decision_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    diagnosis_id TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    coach_action TEXT NOT NULL,
    coach_id TEXT NOT NULL,
    decision_summary TEXT NOT NULL,
    outcome_intent TEXT NOT NULL,
    status TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_training_plans (
    plan_id TEXT PRIMARY KEY,
    athlete_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    constraints JSONB NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kaizo_training_sessions (
    session_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    title TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    blocks JSONB NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
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


def upsert_decision_candidate(candidate: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_decision_candidates
                (candidate_id, diagnosis_id, problem_id, athlete_id, assessment_id,
                 candidate_type, title, rationale, source_diagnosis, status, generated_by, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (candidate_id) DO UPDATE SET
                    title=EXCLUDED.title, rationale=EXCLUDED.rationale,
                    status=EXCLUDED.status, generated_by=EXCLUDED.generated_by""",
                (candidate["candidate_id"], candidate["diagnosis_id"], candidate["problem_id"],
                 candidate["athlete_id"], candidate["assessment_id"], candidate["candidate_type"],
                 candidate["title"], candidate["rationale"], candidate["source_diagnosis"],
                 candidate["status"], candidate["generated_by"], candidate["created_at"]),
            )
        conn.commit()


def list_decision_candidates(diagnosis_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT candidate_id, diagnosis_id, problem_id, athlete_id, assessment_id,
                          candidate_type, title, rationale, source_diagnosis, status,
                          generated_by, created_at
                   FROM kaizo_decision_candidates
                   WHERE diagnosis_id=%s ORDER BY created_at, candidate_id""",
                (diagnosis_id,),
            )
            rows = cur.fetchall()
    return [{
        "candidate_id": r[0], "diagnosis_id": r[1], "problem_id": r[2],
        "athlete_id": r[3], "assessment_id": r[4], "candidate_type": r[5],
        "title": r[6], "rationale": r[7], "source_diagnosis": r[8],
        "status": r[9], "generated_by": r[10], "created_at": r[11]
    } for r in rows]


def list_evidence_linked_diagnoses_for_id(diagnosis_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT diagnosis_id, problem_id, athlete_id, assessment_id,
                                  evidence_ids, diagnosis, diagnosed_by, confidence,
                                  resolution_state, diagnosed_at
                           FROM kaizo_evidence_linked_diagnoses WHERE diagnosis_id=%s""",
                        (diagnosis_id,))
            rows = cur.fetchall()
    return [{"diagnosis_id":r[0],"problem_id":r[1],"athlete_id":r[2],"assessment_id":r[3],
             "evidence_ids":r[4],"diagnosis":r[5],"diagnosed_by":r[6],"confidence":r[7],
             "resolution_state":r[8],"diagnosed_at":r[9]} for r in rows]


def get_decision_candidate(candidate_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT candidate_id, diagnosis_id, problem_id, athlete_id, assessment_id,
                          candidate_type, title, rationale, source_diagnosis, status,
                          generated_by, created_at
                   FROM kaizo_decision_candidates WHERE candidate_id=%s""",
                (candidate_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "candidate_id": row[0], "diagnosis_id": row[1], "problem_id": row[2],
        "athlete_id": row[3], "assessment_id": row[4], "candidate_type": row[5],
        "title": row[6], "rationale": row[7], "source_diagnosis": row[8],
        "status": row[9], "generated_by": row[10], "created_at": row[11],
    }


def upsert_decision_rationale(rationale: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_decision_rationales
                (rationale_id, candidate_id, diagnosis_id, problem_id, athlete_id,
                 assessment_id, rationale, evidence_ids, recorded_by, recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                ON CONFLICT (rationale_id) DO UPDATE SET
                    rationale=EXCLUDED.rationale,
                    evidence_ids=EXCLUDED.evidence_ids,
                    recorded_by=EXCLUDED.recorded_by,
                    recorded_at=EXCLUDED.recorded_at""",
                (
                    rationale["rationale_id"], rationale["candidate_id"],
                    rationale["diagnosis_id"], rationale["problem_id"],
                    rationale["athlete_id"], rationale["assessment_id"],
                    rationale["rationale"], json.dumps(rationale["evidence_ids"]),
                    rationale["recorded_by"], rationale["recorded_at"],
                ),
            )
        conn.commit()


def list_decision_rationales(candidate_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT rationale_id, candidate_id, diagnosis_id, problem_id,
                          athlete_id, assessment_id, rationale, evidence_ids,
                          recorded_by, recorded_at
                   FROM kaizo_decision_rationales
                   WHERE candidate_id=%s ORDER BY recorded_at, rationale_id""",
                (candidate_id,),
            )
            rows = cur.fetchall()
    return [{
        "rationale_id": r[0], "candidate_id": r[1], "diagnosis_id": r[2],
        "problem_id": r[3], "athlete_id": r[4], "assessment_id": r[5],
        "rationale": r[6], "evidence_ids": r[7], "recorded_by": r[8],
        "recorded_at": r[9], "coach_review_required": True,
    } for r in rows]


def upsert_decision_comparison(comparison: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_decision_comparisons
                (comparison_id, diagnosis_id, candidate_ids, alternatives, comparison_status, compared_by, compared_at)
                VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
                ON CONFLICT (comparison_id) DO UPDATE SET
                    candidate_ids=EXCLUDED.candidate_ids,
                    alternatives=EXCLUDED.alternatives,
                    comparison_status=EXCLUDED.comparison_status,
                    compared_by=EXCLUDED.compared_by,
                    compared_at=EXCLUDED.compared_at""",
                (
                    comparison["comparison_id"], comparison["diagnosis_id"],
                    json.dumps(comparison["candidate_ids"]),
                    json.dumps(comparison["alternatives"]),
                    comparison["comparison_status"],
                    comparison["compared_by"], comparison["compared_at"],
                ),
            )
        conn.commit()


def list_decision_comparisons(diagnosis_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT comparison_id, diagnosis_id, candidate_ids, alternatives,
                          comparison_status, compared_by, compared_at
                   FROM kaizo_decision_comparisons
                   WHERE diagnosis_id=%s ORDER BY compared_at, comparison_id""",
                (diagnosis_id,),
            )
            rows = cur.fetchall()
    return [{
        "comparison_id": r[0], "diagnosis_id": r[1], "candidate_ids": r[2],
        "alternatives": r[3], "comparison_status": r[4],
        "compared_by": r[5], "compared_at": r[6],
        "coach_review_required": True,
    } for r in rows]



def upsert_coach_decision_review(review: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_coach_decision_reviews
                (review_id, candidate_id, diagnosis_id, problem_id, athlete_id, assessment_id,
                 action, status, coach_id, override_reason, reviewed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (review_id) DO UPDATE SET
                    action=EXCLUDED.action, status=EXCLUDED.status,
                    coach_id=EXCLUDED.coach_id, override_reason=EXCLUDED.override_reason,
                    reviewed_at=EXCLUDED.reviewed_at""",
                (
                    review["review_id"], review["candidate_id"], review["diagnosis_id"],
                    review["problem_id"], review["athlete_id"], review["assessment_id"],
                    review["action"], review["status"], review["coach_id"],
                    review.get("override_reason"), review["reviewed_at"],
                ),
            )
        conn.commit()


def list_coach_decision_reviews(candidate_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT review_id, candidate_id, diagnosis_id, problem_id, athlete_id,
                          assessment_id, action, status, coach_id, override_reason, reviewed_at
                   FROM kaizo_coach_decision_reviews
                   WHERE candidate_id=%s ORDER BY reviewed_at, review_id""",
                (candidate_id,),
            )
            rows = cur.fetchall()
    return [{
        "review_id": r[0], "candidate_id": r[1], "diagnosis_id": r[2],
        "problem_id": r[3], "athlete_id": r[4], "assessment_id": r[5],
        "action": r[6], "status": r[7], "coach_id": r[8],
        "override_reason": r[9], "reviewed_at": r[10],
        "coach_final_authority": True, "execution_authorized": False,
    } for r in rows]


def upsert_training_plan(plan: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO kaizo_training_plans
                (plan_id,athlete_id,decision_id,title,objective,constraints,status,created_by,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (plan_id) DO UPDATE SET title=EXCLUDED.title,
                objective=EXCLUDED.objective,constraints=EXCLUDED.constraints,status=EXCLUDED.status""",
                (plan["plan_id"],plan["athlete_id"],plan["decision_id"],plan["title"],plan["objective"],
                 json.dumps(plan["constraints"]),plan["status"],plan["created_by"],plan["created_at"]))
        conn.commit()


def get_training_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT plan_id,athlete_id,decision_id,title,objective,constraints,status,created_by,created_at
                           FROM kaizo_training_plans WHERE plan_id=%s""",(plan_id,))
            r=cur.fetchone()
    if not r:
        return None
    return {"plan_id":r[0],"athlete_id":r[1],"decision_id":r[2],"title":r[3],"objective":r[4],
            "constraints":r[5],"status":r[6],"created_by":r[7],"created_at":r[8],
            "coach_final_authority":True,"execution_authorized":False}


def upsert_decision_record(record: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO kaizo_decision_records
                (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                 candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (decision_id) DO UPDATE SET
                    coach_action=EXCLUDED.coach_action, coach_id=EXCLUDED.coach_id,
                    decision_summary=EXCLUDED.decision_summary, outcome_intent=EXCLUDED.outcome_intent,
                    status=EXCLUDED.status, recorded_at=EXCLUDED.recorded_at""",
                (record["decision_id"],record["candidate_id"],record["diagnosis_id"],record["problem_id"],
                 record["athlete_id"],record["assessment_id"],record["candidate_type"],record["coach_action"],
                 record["coach_id"],record["decision_summary"],record["outcome_intent"],record["status"],record["recorded_at"]))
        conn.commit()


def get_decision_record(decision_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                                  candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at
                           FROM kaizo_decision_records WHERE decision_id=%s""",(decision_id,))
            r=cur.fetchone()
    if not r:
        return None
    return {"decision_id":r[0],"candidate_id":r[1],"diagnosis_id":r[2],"problem_id":r[3],"athlete_id":r[4],
            "assessment_id":r[5],"candidate_type":r[6],"coach_action":r[7],"coach_id":r[8],
            "decision_summary":r[9],"outcome_intent":r[10],"status":r[11],"recorded_at":r[12],
            "coach_final_authority":True,"execution_authorized":False}


def list_decision_records(candidate_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                                  candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at
                           FROM kaizo_decision_records WHERE candidate_id=%s ORDER BY recorded_at,decision_id""",
                        (candidate_id,))
            rows=cur.fetchall()
    return [{"decision_id":r[0],"candidate_id":r[1],"diagnosis_id":r[2],"problem_id":r[3],
             "athlete_id":r[4],"assessment_id":r[5],"candidate_type":r[6],"coach_action":r[7],
             "coach_id":r[8],"decision_summary":r[9],"outcome_intent":r[10],"status":r[11],
             "recorded_at":r[12],"coach_final_authority":True,"execution_authorized":False} for r in rows]


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


def upsert_training_session(session: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO kaizo_training_sessions
                (session_id,plan_id,athlete_id,title,duration_minutes,blocks,status,created_by,created_at)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                ON CONFLICT (session_id) DO UPDATE SET title=EXCLUDED.title,
                duration_minutes=EXCLUDED.duration_minutes, blocks=EXCLUDED.blocks,
                status=EXCLUDED.status""",
                (session["session_id"],session["plan_id"],session["athlete_id"],session["title"],
                 session["duration_minutes"],json.dumps(session["blocks"]),session["status"],
                 session["created_by"],session["created_at"]))
        conn.commit()


def get_training_session(session_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT session_id,plan_id,athlete_id,title,duration_minutes,blocks,
                                  status,created_by,created_at
                           FROM kaizo_training_sessions WHERE session_id=%s""",(session_id,))
            row=cur.fetchone()
    if row is None:
        return None
    return {"session_id":row[0],"plan_id":row[1],"athlete_id":row[2],"title":row[3],
            "duration_minutes":row[4],"blocks":row[5],"status":row[6],"created_by":row[7],
            "created_at":row[8]}

