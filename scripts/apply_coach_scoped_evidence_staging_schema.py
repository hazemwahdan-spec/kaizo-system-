"""Apply only the additive Coach evidence schema to an explicitly identified Staging DB."""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse


def main():
    environment = os.getenv("KAIZO_ENVIRONMENT", "").strip().lower()
    database_url = os.getenv("DATABASE_URL", "").strip()
    expected_host = os.getenv("KAIZO_STAGING_DB_HOST", "").strip().lower()
    production_host = os.getenv("KAIZO_PRODUCTION_DB_HOST", "").strip().lower()
    if environment != "staging":
        raise RuntimeError("Refusing schema change: KAIZO_ENVIRONMENT must be exactly 'staging'")
    if not database_url or not expected_host or not production_host:
        raise RuntimeError("Staging DATABASE_URL secret plus trusted Staging and Production DB host variables are required")
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
    if parsed.hostname.lower() != expected_host:
        raise RuntimeError("DATABASE_URL host does not match the trusted KAIZO_STAGING_DB_HOST")
    if parsed.hostname.lower() == production_host:
        raise RuntimeError("Refusing schema change: target host matches the configured Production DB host")

    sys.path.insert(0, os.path.abspath("backend"))
    import persistence
    import coach_scoped_evidence_runtime as scoped

    if not persistence.is_postgres_enabled():
        raise RuntimeError("PostgreSQL persistence mode is not enabled")
    # Never initialize the full Core schema from this narrowly scoped workflow.
    # Require its authoritative parent tables to exist already, then create only
    # the four additive Coach-scoped evidence tables below.
    required_parents = (
        "kaizo_athletes",
        "kaizo_coach_athlete_ownership",
        "kaizo_evidence_records",
        "kaizo_training_sessions",
        "kaizo_audit_logs",
    )
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + ", ".join("to_regclass(%s)" for _ in required_parents),
                tuple(required_parents),
            )
            parent_rows = cur.fetchone()
    missing_parents = [
        name for name, value in zip(required_parents, parent_rows or ())
        if value is None
    ]
    if missing_parents:
        raise RuntimeError(
            "Required existing Staging parent tables are missing; refusing full Core schema initialization: "
            + ", ".join(missing_parents)
        )
    scoped.ensure_schema()

    required = (
        "kaizo_coach_scoped_knowledge",
        "kaizo_coach_scoped_knowledge_links",
        "kaizo_coach_scoped_actor_trace",
        "kaizo_coach_scoped_governance",
    )
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + ", ".join("to_regclass(%s)" for _ in required),
                tuple(required),
            )
            rows = cur.fetchone()
    missing = [name for name, value in zip(required, rows) if value is None]
    if missing:
        raise RuntimeError("Staging schema verification failed; missing: " + ", ".join(missing))
    print("PASS additive Coach evidence schema created and verified on the allowlisted Staging database.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL Staging schema preparation: {exc}", file=sys.stderr)
        sys.exit(1)
