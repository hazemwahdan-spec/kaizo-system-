"""Safety tests for the narrowly scoped Coach evidence Staging schema workflow."""
import importlib.util
from contextlib import contextmanager
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import persistence
import coach_scoped_evidence_runtime as scoped

SCRIPT = ROOT / "scripts" / "apply_coach_scoped_evidence_staging_schema.py"
SPEC = importlib.util.spec_from_file_location("coach_staging_schema_script", SCRIPT)
schema_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(schema_script)


class FakeCursor:
    def __init__(self, missing=None):
        self.missing = missing
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, params=()):
        self.row = tuple(None if item == self.missing else item for item in params)

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, missing=None):
        self.missing = missing

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return FakeCursor(self.missing)


def _configure_staging(monkeypatch, missing=None):
    monkeypatch.setenv("KAIZO_ENVIRONMENT", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql://staging-user:masked@staging-db.example/kaizo")
    monkeypatch.setenv("KAIZO_STAGING_DB_HOST", "staging-db.example")
    monkeypatch.setenv("KAIZO_PRODUCTION_DB_HOST", "production-db.example")
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)

    @contextmanager
    def fake_connection():
        yield FakeConnection(missing)

    monkeypatch.setattr(persistence, "connection", fake_connection)
    monkeypatch.setattr(
        persistence, "initialize",
        lambda: (_ for _ in ()).throw(AssertionError("full Core schema initialization is forbidden")),
    )


def test_staging_schema_workflow_only_calls_scoped_schema_ensure(monkeypatch):
    _configure_staging(monkeypatch)
    calls = []
    monkeypatch.setattr(scoped, "ensure_schema", lambda: calls.append("scoped"))
    schema_script.main()
    assert calls == ["scoped"]


def test_staging_schema_workflow_refuses_missing_parent_tables_without_initializing_core(monkeypatch):
    _configure_staging(monkeypatch, missing="kaizo_coach_athlete_ownership")
    calls = []
    monkeypatch.setattr(scoped, "ensure_schema", lambda: calls.append("scoped"))
    with pytest.raises(RuntimeError, match="Required existing Staging parent tables are missing"):
        schema_script.main()
    assert calls == []
