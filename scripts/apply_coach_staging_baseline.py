"""Create the minimal, additive Coach Staging baseline without broad schema initialization.

This script is restricted to the explicitly allowlisted kaizo_coach_staging
PostgreSQL database. It creates only the base tables required by Coach-scoped
evidence and ownership checks; it never drops, alters, truncates, or seeds data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

EXPECTED_COLUMNS = {
    "kaizo_athletes": {
        "athlete_id", "display_name", "status", "metadata", "created_at", "updated_at",
    },
    "kaizo_audit_logs": {
        "id", "timestamp", "who", "action", "old_value", "new_value", "why", "tenant_id",
    },
    "kaizo_evidence_records": {
        "evidence_id", "subject_type", "subject_id", "evidence_level", "status",
        "source_ref", "claim", "observed_value", "verified_by", "verified_at", "notes",
    },
    "kaizo_training_sessions": {
        "session_id", "plan_id", "athlete_id", "title", "duration_minutes",
        "blocks", "status", "created_by", "created_at",
    },
    "kaizo_coach_athlete_ownership": {
        "athlete_id", "tenant_id", "coach_actor_id", "assigned_at",
    },
}

BASELINE_DDL = (
    """CREATE TABLE IF NOT EXISTS kaizo_athletes (
        athlete_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        status TEXT NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS kaizo_audit_logs (
        id BIGSERIAL PRIMARY KEY,
        timestamp TEXT NOT NULL,
        who TEXT NOT NULL,
        action TEXT NOT NULL,
        old_value JSONB,
        new_value JSONB,
        why TEXT NOT NULL,
        tenant_id TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS kaizo_evidence_records (
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
    )""",
    """CREATE TABLE IF NOT EXISTS kaizo_training_sessions (
        session_id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL,
        athlete_id TEXT NOT NULL,
        title TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL,
        blocks JSONB NOT NULL,
        status TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS kaizo_coach_athlete_ownership (
        athlete_id TEXT PRIMARY KEY
            REFERENCES kaizo_athletes(athlete_id) ON DELETE CASCADE,
        tenant_id TEXT NOT NULL,
        coach_actor_id TEXT NOT NULL,
        assigned_at TEXT NOT NULL,
        CONSTRAINT uq_coach_athlete_scope
            UNIQUE (tenant_id, coach_actor_id, athlete_id)
    )""",
    """CREATE INDEX IF NOT EXISTS idx_kaizo_audit_logs_tenant_id_id
        ON kaizo_audit_logs (tenant_id, id)""",
    """CREATE INDEX IF NOT EXISTS idx_coach_roster_scope
        ON kaizo_coach_athlete_ownership (tenant_id, coach_actor_id, assigned_at)""",
)


def apply_baseline(conn: Any) -> None:
    """Apply and verify the minimal Coach Staging baseline in the current schema."""
    with conn.cursor() as cur:
        for statement in BASELINE_DDL:
            cur.execute(statement)

        cur.execute(
            """SELECT table_name, column_name
               FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = ANY(%s)""",
            (list(EXPECTED_COLUMNS),),
        )
        actual: dict[str, set[str]] = {}
        for table_name, column_name in cur.fetchall():
            actual.setdefault(str(table_name), set()).add(str(column_name))

        missing = [
            f"{table}.{column}"
            for table, columns in EXPECTED_COLUMNS.items()
            for column in sorted(columns - actual.get(table, set()))
        ]
        if missing:
            raise RuntimeError(
                "Coach Staging baseline verification failed; missing columns: "
                + ", ".join(missing)
            )

        cur.execute(
            """SELECT EXISTS (
                   SELECT 1
                   FROM pg_constraint
                   WHERE contype = 'f'
                     AND conrelid = to_regclass('kaizo_coach_athlete_ownership')
                     AND confrelid = to_regclass('kaizo_athletes')
               )"""
        )
        if not cur.fetchone()[0]:
            raise RuntimeError(
                "Coach Staging baseline verification failed; ownership-to-athlete foreign key is missing"
            )


def main() -> None:
    environment = os.getenv("KAIZO_ENVIRONMENT", "").strip().lower()
    database_url = os.getenv("DATABASE_URL", "").strip()
    staging_host = os.getenv("KAIZO_STAGING_DB_HOST", "").strip()
    production_host = os.getenv("KAIZO_PRODUCTION_DB_HOST", "").strip()

    if environment != "staging":
        raise RuntimeError("Refusing baseline: KAIZO_ENVIRONMENT must be exactly 'staging'")
    if not database_url or not staging_host or not production_host:
        raise RuntimeError(
            "Staging DATABASE_URL plus trusted Staging and Production DB host variables are required"
        )

    scripts_dir = str(Path(__file__).resolve().parent)
    backend_dir = str(Path(__file__).resolve().parents[1] / "backend")
    sys.path.insert(0, scripts_dir)
    sys.path.insert(0, backend_dir)

    from apply_coach_scoped_evidence_staging_schema import validate_staging_database_target
    import persistence

    validate_staging_database_target(database_url, staging_host, production_host)
    if not persistence.is_postgres_enabled():
        raise RuntimeError("Coach Staging baseline requires KAIZO_PERSISTENCE_MODE=postgres")

    with persistence.connection() as conn:
        apply_baseline(conn)

    print(
        "PASS: minimal Coach Staging baseline created and verified "
        "on the allowlisted kaizo_coach_staging database; no data was inserted."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL Coach Staging baseline: {exc}", file=sys.stderr)
        sys.exit(1)
