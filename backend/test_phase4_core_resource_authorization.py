"""HTTP acceptance for Phase 4 protection on the actual Core FastAPI app."""
import sys
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from fastapi.testclient import TestClient
import pytest

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


@pytest.fixture(autouse=True)
def isolate_authorization_tests_from_audit_store(monkeypatch, request):
    # Route security assertions below use mocked identity/resource stores. The
    # separate durable-audit tests exercise the real PostgreSQL audit adapter.
    if request.node.name not in {
        "test_authorization_decisions_are_durably_audited",
        "test_authorization_audit_store_failure_fails_closed",
    }:
        monkeypatch.setattr(authz, "_audit_authorization", lambda **_: None)


def test_authorization_decisions_are_durably_audited():
    correlation_id = "phase4-authorization-audit-test"
    principal = _principal()
    authz._audit_authorization(
        principal=principal,
        resource_type="athlete",
        resource_id="audit-test-athlete",
        action="read",
        decision="deny",
        reason_code="RESOURCE_TENANT_SCOPE_DENIED",
        request_route="/api/v1/athletes/{athlete_id}",
        correlation_id=correlation_id,
    )
    from phase4_identity_store import list_authorization_audit
    rows = list_authorization_audit(correlation_id=correlation_id)
    assert any(
        row["decision"] == "deny"
        and row["reason_code"] == "RESOURCE_TENANT_SCOPE_DENIED"
        and row["resource_id"] == "audit-test-athlete"
        for row in rows
    )


def test_authorization_audit_store_failure_fails_closed(monkeypatch):
    import phase4_identity_store

    def unavailable(**_):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(phase4_identity_store, "append_authorization_audit", unavailable)
    with pytest.raises(Exception) as error:
        authz._audit_authorization(
            principal=_principal(),
            resource_type="athlete",
            resource_id="audit-fail-closed",
            action="read",
            decision="allow",
            reason_code="RESOURCE_TENANT_SCOPE_VALID",
            request_route="/api/v1/athletes/{athlete_id}",
        )
    assert getattr(error.value, "status_code", None) == 503


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


def test_actual_create_assessment_rejects_invalid_identity_without_write(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(
        boundary, "resolve_bearer_principal",
        lambda _: (_ for _ in ()).throw(IdentityNotConfiguredError("invalid bearer")),
    )
    writes = []
    monkeypatch.setattr(main.persistence, "upsert_assessment", lambda item: writes.append(item))
    response = client.post(
        "/api/v1/assessments",
        json={"athlete_id": "athlete-1", "template_id": "TPL", "measurements": {"x": 1}, "recorded_by": "coach"},
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 401
    assert writes == []


def test_actual_patch_athlete_denies_wrong_tenant_before_read_or_write(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(authz, "get_resource_tenant", lambda **_: "academy-b")
    reads, writes = [], []
    monkeypatch.setattr(main.persistence, "get_athlete", lambda athlete_id: reads.append(athlete_id) or {"athlete_id": athlete_id})
    monkeypatch.setattr(main.persistence, "upsert_athlete", lambda item: writes.append(item))
    response = client.patch(
        "/api/v1/athletes/athlete-from-other-academy",
        json={"display_name": "Unauthorized update"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert reads == []
    assert writes == []


def test_actual_create_assessment_denies_cross_tenant_before_athlete_read_or_write(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(authz, "get_resource_tenant", lambda **_: "academy-b")
    reads, writes = [], []
    monkeypatch.setattr(main.persistence, "get_athlete", lambda athlete_id: reads.append(athlete_id) or {"athlete_id": athlete_id})
    monkeypatch.setattr(main.persistence, "upsert_assessment", lambda item: writes.append(item))
    response = client.post(
        "/api/v1/assessments",
        json={"athlete_id": "athlete-from-other-academy", "template_id": "TPL", "measurements": {"x": 1}, "recorded_by": "coach"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert reads == []
    assert writes == []


def test_core_routes_fail_closed_when_oidc_gate_is_disabled(monkeypatch):
    monkeypatch.delenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", raising=False)
    response = client.get("/api/v1/athletes/any-id")
    assert response.status_code == 503
