"""Regression tests for fail-closed global evidence publisher authorization."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
import persistence
import evidence_authorization

app = main.app
client = TestClient(app)


def publisher():
    return SimpleNamespace(
        actor_id="auth0|approved-publisher",
        role="publisher",
        tenant_id="global",
        verified=True,
        source="oidc_jwt",
    )


def _override_publisher():
    app.dependency_overrides[evidence_authorization.require_global_evidence_publisher] = publisher


def _clear_override():
    app.dependency_overrides.pop(evidence_authorization.require_global_evidence_publisher, None)


def test_evidence_list_is_denied_when_publisher_gate_is_disabled(monkeypatch):
    monkeypatch.delenv("KAIZO_EVIDENCE_PUBLISHER_ENABLED", raising=False)
    response = client.get("/api/v1/evidence")
    assert response.status_code == 503


def test_evidence_detail_is_denied_when_publisher_gate_is_disabled(monkeypatch):
    monkeypatch.delenv("KAIZO_EVIDENCE_PUBLISHER_ENABLED", raising=False)
    response = client.get("/api/v1/evidence/containment-probe")
    assert response.status_code == 503


def test_evidence_write_is_denied_when_publisher_gate_is_disabled(monkeypatch):
    monkeypatch.delenv("KAIZO_EVIDENCE_PUBLISHER_ENABLED", raising=False)
    response = client.post("/api/v1/evidence", json={
        "evidence_id": "containment-probe",
        "subject_type": "rule",
        "subject_id": "global-rule",
        "evidence_level": "E1",
        "status": "UNVERIFIED",
        "claim": "containment regression probe",
        "verified_by": "caller-supplied-value",
    })
    assert response.status_code == 503


def test_publisher_gate_rejects_non_publisher_oidc_role(monkeypatch):
    monkeypatch.setenv("KAIZO_EVIDENCE_PUBLISHER_ENABLED", "true")
    monkeypatch.setattr(
        evidence_authorization,
        "resolve_bearer_principal",
        lambda _: SimpleNamespace(
            actor_id="auth0|coach", role="coach", tenant_id="global",
            verified=True, source="oidc_jwt",
        ),
    )
    with pytest.raises(HTTPException) as exc:
        evidence_authorization.require_global_evidence_publisher("Bearer signed")
    assert exc.value.status_code == 403


def test_publisher_gate_rejects_wrong_global_tenant(monkeypatch):
    monkeypatch.setenv("KAIZO_EVIDENCE_PUBLISHER_ENABLED", "true")
    monkeypatch.setattr(
        evidence_authorization,
        "resolve_bearer_principal",
        lambda _: SimpleNamespace(
            actor_id="auth0|publisher", role="publisher", tenant_id="academy-a",
            verified=True, source="oidc_jwt",
        ),
    )
    with pytest.raises(HTTPException) as exc:
        evidence_authorization.require_global_evidence_publisher("Bearer signed")
    assert exc.value.status_code == 403


def test_verified_publisher_write_ignores_client_verified_by_and_audits_atomically(monkeypatch):
    _override_publisher()
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    persisted = {}
    monkeypatch.setattr(
        persistence,
        "upsert_evidence_with_audit",
        lambda record, **kwargs: persisted.update(record=record, audit=kwargs),
    )
    try:
        response = client.post("/api/v1/evidence", json={
            "evidence_id": "global-rule-evidence",
            "subject_type": "rule",
            "subject_id": "global-rule-001",
            "evidence_level": "E2",
            "status": "VERIFIED",
            "source_ref": "rule://approved-source",
            "claim": "Verified global rule source",
            "observed_value": {"threshold": 5},
            "verified_by": "forged-client-value",
        })
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["verified_by"] == "auth0|approved-publisher"
        assert persisted["record"]["verified_by"] == "auth0|approved-publisher"
        assert persisted["audit"]["who"] == "auth0|approved-publisher"
        assert persisted["audit"]["action"] == "EVIDENCE_RECORDED"
    finally:
        _clear_override()


def test_publisher_cannot_write_tenant_owned_evidence(monkeypatch):
    _override_publisher()
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    try:
        response = client.post("/api/v1/evidence", json={
            "evidence_id": "tenant-assessment-evidence",
            "subject_type": "assessment",
            "subject_id": "assessment-001",
            "evidence_level": "E2",
            "status": "VERIFIED",
            "claim": "Tenant-owned evidence must use scoped route",
        })
        assert response.status_code == 403
    finally:
        _clear_override()


def test_publisher_list_only_returns_global_evidence(monkeypatch):
    _override_publisher()
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(persistence, "list_evidence", lambda _subject_id=None: [
        {"evidence_id": "rule-1", "subject_type": "rule", "subject_id": "r1"},
        {"evidence_id": "assessment-1", "subject_type": "assessment", "subject_id": "a1"},
        {"evidence_id": "catalog-1", "subject_type": "catalog", "subject_id": "c1"},
    ])
    try:
        response = client.get("/api/v1/evidence")
        assert response.status_code == 200, response.text
        assert {item["evidence_id"] for item in response.json()["records"]} == {"rule-1", "catalog-1"}
    finally:
        _clear_override()


def test_publisher_cannot_read_tenant_owned_evidence(monkeypatch):
    _override_publisher()
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(persistence, "get_evidence", lambda _evidence_id: {
        "evidence_id": "assessment-1", "subject_type": "assessment", "subject_id": "a1"
    })
    try:
        response = client.get("/api/v1/evidence/assessment-1")
        assert response.status_code == 404
    finally:
        _clear_override()
