"""Tenant/resource authorization regressions for the seven Phase 4 domain runtimes."""
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from phase4_identity_boundary import Principal, require_phase4_principal
from phase4_domain_authorization import require_phase4_domain_access


def test_caller_cannot_spoof_domain_actor_or_tenant():
    previous = main.app.dependency_overrides.get(require_phase4_principal)
    main.app.dependency_overrides[require_phase4_principal] = lambda: Principal(
        actor_id="verified-subject", role="coach", tenant_id="tenant-a",
        resource_owner_id=None, verified=True, source="test",
    )
    client = TestClient(main.app)
    try:
        with patch.dict(os.environ, {"KAIZO_PERSISTENCE_MODE": "memory"}):
            actor = client.post("/api/v1/competition/events", json={
                "event_name": "event", "date": "2026-11-12", "context": {"level": "club"},
                "created_by": "attacker-subject",
            })
            assert actor.status_code == 403
            assert actor.json()["detail"]["reason_code"] == "actor_identity_mismatch"

            tenant = client.post("/api/v1/competition/events", json={
                "event_name": "event", "date": "2026-11-12", "context": {"level": "club"},
                "created_by": "verified-subject", "tenant_id": "tenant-b",
            })
            assert tenant.status_code == 403
            assert tenant.json()["detail"]["reason_code"] == "tenant_mismatch"
    finally:
        if previous is None:
            main.app.dependency_overrides.pop(require_phase4_principal, None)
        else:
            main.app.dependency_overrides[require_phase4_principal] = previous


def test_domain_access_fails_closed_without_durable_ownership_store():
    previous_principal = main.app.dependency_overrides.get(require_phase4_principal)
    previous_domain = main.app.dependency_overrides.pop(require_phase4_domain_access, None)
    main.app.dependency_overrides[require_phase4_principal] = lambda: Principal(
        actor_id="verified-subject", role="coach", tenant_id="tenant-a",
        resource_owner_id=None, verified=True, source="test",
    )
    client = TestClient(main.app)
    try:
        with patch.dict(os.environ, {"KAIZO_PERSISTENCE_MODE": "memory"}):
            response = client.post("/api/v1/competition/readiness", json={
                "athlete_id": "athlete-not-bound", "event_id": "event-not-bound",
                "indicators": {"randori": 5}, "assessed_by": "verified-subject",
            })
            assert response.status_code == 503
            assert "PostgreSQL" in response.json()["detail"]
    finally:
        if previous_principal is None:
            main.app.dependency_overrides.pop(require_phase4_principal, None)
        else:
            main.app.dependency_overrides[require_phase4_principal] = previous_principal
        if previous_domain is not None:
            main.app.dependency_overrides[require_phase4_domain_access] = previous_domain
