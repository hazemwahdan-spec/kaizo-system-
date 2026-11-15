"""Apply only the additive Coach evidence schema to an explicitly identified Staging DB."""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse


def main():
    environment = os.getenv("KAIZO_ENVIRONMENT", "").strip().lower()
    database_url = os.getenv("DATABASE_URL", "").strip()
    expected_host = os.getenv("KAIZO_STAGING_DB_HOST", "").strip().lower()
    if environment != "staging":
        raise RuntimeError("Refusing schema change: KAIZO_ENVIRONMENT must be exactly 'staging'")
    if not database_url or not expected_host:
        raise RuntimeError("Staging DATABASE_URL secret and KAIZO_STAGING_DB_HOST variable are required")
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
    if parsed.hostname.lower() != expected_host:
        raise RuntimeError("DATABASE_URL host does not match the trusted KAIZO_STAGING_DB_HOST")

    sys.path.insert(0, os.path.abspath("backend"))
    import persistence
    import coach_scoped_evidence_runtime as scoped

    if not persistence.is_postgres_enabled():
        raise RuntimeError("PostgreSQL persistence mode is not enabled")
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
