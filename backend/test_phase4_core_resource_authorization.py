"""HTTP acceptance for Phase 4 protection on the actual Core FastAPI app."""
import sys
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from fastapi.testclient import TestClient

from backend import main
import phase4_identity_boundary as boundary
import phase4_core_resource_authorization as authz
from productization.identity import IdentityNotConfiguredError, Principal


client = TestClient(main.app)


def _principal(role="coach", tenant_id="academy-a"):
    return Principal(
        actor_id="oidc|phase4-test-coach",
        role=role,
        tenant_id=tenant_id,
        resource_owner_id=None,
        verified=True,
        source="oidc_jwt",
    )


def test_actual_create_athlete_rejects_missing_or_invalid_identity_without_write(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(
        boundary, "resolve_bearer_principal",
        lambda _: (_ for _ in ()).throw(IdentityNotConfiguredError("invalid bearer")),
    )
    writes = []
    monkeypatch.setattr(main.persistence, "upsert_athlete", lambda athlete: writes.append(athlete))
    response = client.post(
        "/api/v1/athletes",
        json={"display_name": "Should Not Be Created", "metadata": {}},
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401
    assert writes == []


def test_actual_get_athlete_denies_wrong_tenant_before_resource_read(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(
        authz, "has_active_membership", lambda **_: True
    )
    monkeypatch.setattr(
        authz, "get_resource_tenant", lambda **_: "academy-b"
    )
    reads = []
    monkeypatch.setattr(
        main.persistence, "get_athlete",
        lambda athlete_id: reads.append(athlete_id) or {"athlete_id": athlete_id},
    )
    response = client.get(
        "/api/v1/athletes/athlete-from-other-academy",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert reads == []


def test_actual_get_assessment_denies_cross_tenant_before_assessment_read(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(authz, "get_resource_tenant", lambda **_: "academy-b")
    monkeypatch.setattr(main.persistence, "is_postgres_enabled", lambda: True)

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, *_args): pass
        def fetchone(self): return ("athlete-from-other-academy",)

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()

    monkeypatch.setattr(main.persistence, "connection", lambda: Connection())
    reads = []
    monkeypatch.setattr(
        main.persistence, "get_assessment",
        lambda assessment_id: reads.append(assessment_id) or {"assessment_id": assessment_id},
    )
    response = client.get(
        "/api/v1/assessments/assessment-from-other-academy",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert reads == []


def test_core_routes_fail_closed_when_oidc_gate_is_disabled(monkeypatch):
    monkeypatch.delenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", raising=False)
    response = client.get("/api/v1/athletes/any-id")
    assert response.status_code == 503
