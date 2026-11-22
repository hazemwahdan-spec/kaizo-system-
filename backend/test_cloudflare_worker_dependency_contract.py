"""Guard the Python Worker dependency split across CPython and Pyodide."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_root_worker_dependencies_are_python_314_compatible():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]

    assert "uvicorn[standard]==0.34.0; python_version < '3.14'" in dependencies
    assert (
        "psycopg[binary]==3.2.13; python_version < '3.14' "
        "and sys_platform != 'emscripten'"
    ) in dependencies
    assert (
        "psycopg==3.2.13; python_version >= '3.14' "
        "and sys_platform != 'emscripten'"
    ) in dependencies

    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert 'uvicorn[standard]==0.34.0; python_version < "3.14"' in requirements
    assert (
        'psycopg[binary]==3.2.13; python_version < "3.14" '
        'and sys_platform != "emscripten"'
    ) in requirements
    assert (
        'psycopg==3.2.13; python_version >= "3.14" '
        'and sys_platform != "emscripten"'
    ) in requirements


def test_native_backend_manifests_use_the_same_supported_psycopg_release():
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    project = tomllib.loads(
        (ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert "psycopg[binary]==3.2.13" in requirements
    assert "psycopg[binary]==3.2.13" in project["project"]["dependencies"]
    assert "psycopg[binary]==3.2.3" not in requirements
    assert "psycopg[binary]==3.2.3" not in project["project"]["dependencies"]
