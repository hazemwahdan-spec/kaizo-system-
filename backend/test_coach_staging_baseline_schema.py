"""PostgreSQL integration test for the minimal Coach Staging baseline."""
import importlib.util
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_coach_staging_baseline.py"
SPEC = importlib.util.spec_from_file_location("coach_staging_baseline", SCRIPT)
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)


def test_minimal_baseline_is_additive_verified_and_idempotent(monkeypatch):
    import os

    database_url = os.environ["DATABASE_URL"]
    schema_name = "kaizo_coach_baseline_test"

    with psycopg.connect(database_url) as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
        conn.execute(f"SET search_path TO {schema_name}")

        baseline.apply_baseline(conn)
        baseline.apply_baseline(conn)

        cur = conn.cursor()
        cur.execute(
            """SELECT table_name
               FROM information_schema.tables
               WHERE table_schema = current_schema()
                 AND table_type = 'BASE TABLE'"""
        )
        tables = {row[0] for row in cur.fetchall()}
        assert tables == set(baseline.EXPECTED_COLUMNS)

        cur.execute(
            """SELECT EXISTS (
                   SELECT 1
                   FROM pg_constraint
                   WHERE contype = 'f'
                     AND conrelid = to_regclass('kaizo_coach_athlete_ownership')
                     AND confrelid = to_regclass('kaizo_athletes')
               )"""
        )
        assert cur.fetchone()[0] is True

        cur.execute("SELECT COUNT(*) FROM kaizo_athletes")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM kaizo_audit_logs")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM kaizo_evidence_records")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM kaizo_training_sessions")
        assert cur.fetchone()[0] == 0
