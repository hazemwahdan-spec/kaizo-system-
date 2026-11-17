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
import staging_schema_guard

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
    monkeypatch.setenv("DATABASE_URL", "postgresql://staging-user:masked@staging-db.example/kaizo_coach_staging")
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
    with pytest.raises(RuntimeError, match="Required pre-provisioned Staging tables are missing"):
        schema_script.main()
    assert calls == []


def test_worker_startup_never_runs_core_schema_ddl():
    worker_source = (ROOT / "cloudflare_worker.py").read_text()
    assert "persistence.initialize()" not in worker_source
    assert "persistence.check_connection()" in worker_source
    assert "staging_schema_guard.verify_required_tables" in worker_source
    assert "CORE_DATABASE_STARTUP.update" in worker_source
    assert "refuses Production deployments" in worker_source
    assert set(staging_schema_guard.COACH_EVIDENCE_TABLES) == {
        "kaizo_coach_scoped_knowledge",
        "kaizo_coach_scoped_knowledge_links",
        "kaizo_coach_scoped_actor_trace",
        "kaizo_coach_scoped_governance",
    }

 
def test_staging_schema_workflow_refuses_an_unexpected_database_name(monkeypatch):
    _configure_staging(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://staging-user:masked@staging-db.example/not-coach-staging",
    )
    calls = []
    monkeypatch.setattr(scoped, "ensure_schema", lambda: calls.append("scoped"))
    with pytest.raises(RuntimeError, match="target database must be exactly 'kaizo_coach_staging'"):
        schema_script.main()
    assert calls == []


def test_worker_forces_memory_mode_before_core_import_to_prevent_implicit_ddl():
    worker_source = (ROOT / "cloudflare_worker.py").read_text()
    main_source = (ROOT / "backend" / "main.py").read_text()
    memory_guard = worker_source.index('os.environ["KAIZO_PERSISTENCE_MODE"] = "memory"')
    database_guard = worker_source.index('os.environ.pop("DATABASE_URL", None)')
    core_import = worker_source.index("from app import app")
    assert memory_guard < core_import
    assert database_guard < core_import
    # The Core module still has legacy import-time initialization; the Worker
    # must neutralize its environment before importing that module.
    assert "if persistence.is_postgres_enabled():" in main_source
    assert "persistence.initialize()" in main_source


def test_worker_accepts_only_the_allowlisted_staging_hyperdrive_target():
    assert staging_schema_guard.verify_staging_hyperdrive_target(
        "postgresql://worker:masked@staging-db.example:5432/kaizo_coach_staging?sslmode=require",
        "staging-db.example",
        "production-db.example",
        "kaizo_coach_staging",
    ) == ("staging-db.example", "kaizo_coach_staging")


@pytest.mark.parametrize(
    ("connection_string", "staging_host", "production_host", "message"),
    [
        ("postgresql://worker:masked@production-db.example/kaizo_coach_staging", "staging-db.example", "production-db.example", "does not match the trusted Staging"),
        ("postgresql://worker:masked@staging-db.example/kaizo_coach_staging", "", "production-db.example", "Trusted Staging and Production"),
        ("postgresql://worker:masked@staging-db.example/kaizo_coach_staging", "staging-db.example", "staging-db.example", "must differ"),
        ("postgresql://worker:masked@staging-db.example/not-coach-staging", "staging-db.example", "production-db.example", "database must be exactly"),
        ("https://staging-db.example/kaizo_coach_staging", "staging-db.example", "production-db.example", "PostgreSQL URL"),
    ],
)
def test_worker_rejects_untrusted_hyperdrive_targets(
    connection_string, staging_host, production_host, message,
):
    with pytest.raises(RuntimeError, match=message):
        staging_schema_guard.verify_staging_hyperdrive_target(
            connection_string, staging_host, production_host, "kaizo_coach_staging"
        )


def test_worker_requires_trusted_database_host_allowlist_before_hyperdrive_use():
    worker_source = (ROOT / "cloudflare_worker.py").read_text()
    workflow_source = (ROOT / ".github" / "workflows" / "cloudflare-worker-staging-deploy.yml").read_text()
    assert "verify_staging_hyperdrive_target" in worker_source
    assert 'KAIZO_STAGING_DB_HOST: ${{ vars.KAIZO_STAGING_DB_HOST }}' in workflow_source
    assert 'KAIZO_PRODUCTION_DB_HOST: ${{ vars.KAIZO_PRODUCTION_DB_HOST }}' in workflow_source
    assert "environment: staging" in workflow_source
