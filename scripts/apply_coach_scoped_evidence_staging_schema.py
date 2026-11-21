"""Apply only the four additive Coach evidence tables to an explicitly identified Staging DB.

This guarded preparation is Staging-only and deliberately refuses broad baseline DDL.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import parse_qsl, unquote, urlparse


EXPECTED_STAGING_DATABASE = "kaizo_coach_staging"


def validate_staging_database_target(
    database_url: str, expected_host: str, production_host: str
) -> tuple[str, str]:
    """Fail closed unless both the Staging host and exact database are allowlisted."""
    parsed = urlparse(str(database_url or "").strip())
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL with a hostname")

    target_host = parsed.hostname.lower().rstrip(".")
    staging_host = str(expected_host or "").strip().lower().rstrip(".")
    trusted_production_host = str(production_host or "").strip().lower().rstrip(".")
    if not staging_host or not trusted_production_host:
        raise RuntimeError("Trusted Staging and Production DB host variables are required")
    if staging_host == trusted_production_host:
        raise RuntimeError("Refusing schema change: trusted Staging and Production DB hosts must differ")
    if target_host == trusted_production_host:
        raise RuntimeError("Refusing schema change: target host matches the configured Production DB host")
    if target_host != staging_host:
        raise RuntimeError("DATABASE_URL host does not match the trusted KAIZO_STAGING_DB_HOST")

    # libpq permits target parameters such as host, hostaddr and dbname in
    # the URI query string. Reject them so they cannot override the validated
    # authority host or database path when psycopg opens the connection.
    query_keys = {
        key.lower()
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    }
    forbidden_target_overrides = query_keys & {
        "host", "hostaddr", "port", "dbname", "service", "servicefile",
    }
    if forbidden_target_overrides:
        names = ", ".join(sorted(forbidden_target_overrides))
        raise RuntimeError(
            "DATABASE_URL query must not override connection target parameters: " + names
        )

    database_name = unquote(parsed.path.lstrip("/"))
    if not database_name or "/" in database_name:
        raise RuntimeError("DATABASE_URL must identify exactly one PostgreSQL database")
    if database_name != EXPECTED_STAGING_DATABASE:
        raise RuntimeError(
            "Refusing schema change: target database must be exactly 'kaizo_coach_staging'"
        )
    return target_host, database_name


def main():
    environment = os.getenv("KAIZO_ENVIRONMENT", "").strip().lower()
    database_url = os.getenv("DATABASE_URL", "").strip()
    expected_host = os.getenv("KAIZO_STAGING_DB_HOST", "").strip()
    production_host = os.getenv("KAIZO_PRODUCTION_DB_HOST", "").strip()
    if environment != "staging":
        raise RuntimeError("Refusing schema change: KAIZO_ENVIRONMENT must be exactly 'staging'")
    if not database_url or not expected_host or not production_host:
        raise RuntimeError("Staging DATABASE_URL secret plus trusted Staging and Production DB host variables are required")
    validate_staging_database_target(database_url, expected_host, production_host)

    sys.path.insert(0, os.path.abspath("backend"))
    import persistence
    import coach_scoped_evidence_runtime as scoped

    if not persistence.is_postgres_enabled():
        raise RuntimeError("PostgreSQL persistence mode is not enabled")

    # Do not call persistence.initialize(): it applies the repository-wide
    # SCHEMA_SQL (many unrelated tables and ALTERs), which exceeds this
    # workflow's four-table Staging scope. Fail closed unless prerequisites
    # already exist from the separately managed Staging baseline.
    prerequisites = (
        "kaizo_coach_athlete_ownership",
        "kaizo_evidence_records",
        "kaizo_audit_logs",
    )
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + ", ".join("to_regclass(%s)" for _ in prerequisites),
                tuple(prerequisites),
            )
            rows = cur.fetchone()
    missing_prerequisites = [name for name, value in zip(prerequisites, rows) if value is None]
    if missing_prerequisites:
        raise RuntimeError(
            "Staging baseline prerequisites are missing; refusing broad schema initialization: "
            + ", ".join(missing_prerequisites)
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
    print("PASS: exactly four additive Coach evidence tables created and verified on the allowlisted kaizo_coach_staging database.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL Staging schema preparation: {exc}", file=sys.stderr)
        sys.exit(1)
