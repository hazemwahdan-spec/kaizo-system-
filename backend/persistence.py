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

CREATE TABLE IF NOT EXISTS kaizo_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    who TEXT NOT NULL,
    action TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    why TEXT NOT NULL
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
