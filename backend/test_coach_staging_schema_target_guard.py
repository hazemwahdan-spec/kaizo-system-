"""Offline safety tests for the guarded Coach Staging database target."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_coach_scoped_evidence_staging_schema.py"
SPEC = importlib.util.spec_from_file_location("coach_staging_schema_target_guard", SCRIPT)
schema_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(schema_guard)


def test_accepts_only_the_allowlisted_staging_host_and_database():
    assert schema_guard.validate_staging_database_target(
        "postgresql://staging-user:masked@staging-db.example:5432/kaizo_coach_staging?sslmode=require",
        "staging-db.example",
        "production-db.example",
    ) == ("staging-db.example", "kaizo_coach_staging")


@pytest.mark.parametrize(
    ("database_url", "staging_host", "production_host", "message"),
    [
        (
            "postgresql://user:masked@production-db.example:5432/kaizo_coach_staging",
            "staging-db.example",
            "production-db.example",
            "configured Production DB host",
        ),
        (
            "postgresql://user:masked@other-db.example:5432/kaizo_coach_staging",
            "staging-db.example",
            "production-db.example",
            "does not match the trusted KAIZO_STAGING_DB_HOST",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/neondb",
            "staging-db.example",
            "production-db.example",
            "target database must be exactly",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/",
            "staging-db.example",
            "production-db.example",
            "identify exactly one PostgreSQL database",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/kaizo_coach_staging?host=production-db.example",
            "staging-db.example",
            "production-db.example",
            "query must not override connection target parameters",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/kaizo_coach_staging?hostaddr=203.0.113.10",
            "staging-db.example",
            "production-db.example",
            "query must not override connection target parameters",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/kaizo_coach_staging?dbname=production",
            "staging-db.example",
            "production-db.example",
            "query must not override connection target parameters",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/kaizo_coach_staging?service=production",
            "staging-db.example",
            "production-db.example",
            "query must not override connection target parameters",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/kaizo_coach_staging?servicefile=%2Ftmp%2Fpg_service.conf",
            "staging-db.example",
            "production-db.example",
            "query must not override connection target parameters",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/kaizo_coach_staging?%68ost=production-db.example",
            "staging-db.example",
            "production-db.example",
            "query must not override connection target parameters",
        ),
        (
            "mysql://user:masked@staging-db.example:3306/kaizo_coach_staging",
            "staging-db.example",
            "production-db.example",
            "PostgreSQL URL",
        ),
        (
            "postgresql://user:masked@staging-db.example:5432/kaizo_coach_staging",
            "staging-db.example",
            "staging-db.example",
            "hosts must differ",
        ),
    ],
)
def test_rejects_wrong_or_ambiguous_database_targets(
    database_url, staging_host, production_host, message
):
    with pytest.raises(RuntimeError, match=message):
        schema_guard.validate_staging_database_target(
            database_url, staging_host, production_host
        )
