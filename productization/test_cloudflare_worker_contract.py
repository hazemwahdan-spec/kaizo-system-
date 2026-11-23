"""Static contract checks for the isolated Cloudflare staging runtime."""
import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cloudflare_worker_uses_existing_fastapi_and_frontend():
    config = json.loads((ROOT / "wrangler.jsonc").read_text(encoding="utf-8"))
    assert config["main"] == "cloudflare_worker.py"
    assert config["compatibility_date"] >= "2026-09-08"
    assert "python_workers" in config["compatibility_flags"]
    assert config["assets"]["directory"] == "./frontend"
    assert "/api/*" in config["assets"]["run_worker_first"]


def test_cloudflare_staging_is_isolated_from_production_database():
    config = json.loads((ROOT / "wrangler.jsonc").read_text(encoding="utf-8"))
    worker = (ROOT / "cloudflare_worker.py").read_text(encoding="utf-8")
    assert config["vars"]["KAIZO_ENVIRONMENT"] == "staging"
    assert config["vars"]["KAIZO_PERSISTENCE_MODE"] == "memory"
    assert "HYPERDRIVE" in worker
    assert "hyperdrive.connectionString" not in worker
    assert 'os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"' not in worker
    assert 'os.environ.pop("DATABASE_URL", None)' in worker
    assert "persistence.initialize()" not in worker
    assert "asyncio.Lock()" not in worker
    assert "DATABASE_URL" not in json.dumps(config)


def test_cloudflare_runtime_keeps_oidc_identity_enforced():
    config = json.loads((ROOT / "wrangler.jsonc").read_text(encoding="utf-8"))
    assert config["vars"]["KAIZO_IDENTITY_MODE"] == "oidc"
    assert config["vars"]["KAIZO_OIDC_ISSUER"] == "https://kaizo-system.us.auth0.com/"
    assert config["vars"]["KAIZO_OIDC_AUDIENCE"] == "https://api.kaizo.system"


def test_pyodide_uses_non_binary_psycopg_driver():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    assert any("psycopg[binary]" in item and "python_version < '3.14'" in item for item in dependencies)
    assert any(item == "psycopg==3.2.13; python_version >= '3.14' and sys_platform != 'emscripten'" for item in dependencies)
    dev_dependencies = project["dependency-groups"]["dev"]
    assert any(item.startswith("workers-py;") and "python_version >= '3.11'" in item for item in dev_dependencies)
    assert any(item.startswith("workers-runtime-sdk;") and "python_version >= '3.11'" in item for item in dev_dependencies)
