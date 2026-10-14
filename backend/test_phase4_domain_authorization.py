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


def test_postgres_domain_resource_binding_allows_same_tenant_and_denies_cross_tenant():
    from uuid import uuid4
    import persistence

    suffix = uuid4().hex
    tenant_a, tenant_b = "domain-a-" + suffix, "domain-b-" + suffix
    subject = "oidc|domain-coach-" + suffix
    own_resource, foreign_resource = "knowledge-own-" + suffix, "knowledge-foreign-" + suffix
    trace_own, trace_foreign = "domain-own-" + suffix, "domain-foreign-" + suffix
    principal = Principal(
        actor_id=subject, role="coach", tenant_id=tenant_a,
        resource_owner_id=None, verified=True, source="oidc_jwt",
    )
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kaizo_tenants(tenant_id,display_name) VALUES (%s,%s),(%s,%s)",
                (tenant_a, tenant_a, tenant_b, tenant_b),
            )
            cur.execute(
                """INSERT INTO kaizo_tenant_memberships(tenant_id,subject_id,role,status)
                   VALUES (%s,%s,'coach','ACTIVE')""",
                (tenant_a, subject),
            )
            cur.execute(
                """INSERT INTO kaizo_resource_tenant_bindings
                   (resource_type,resource_id,tenant_id,bound_by_subject)
                   VALUES ('knowledge',%s,%s,%s),('knowledge',%s,%s,%s)""",
                (own_resource, tenant_a, subject, foreign_resource, tenant_b, subject),
            )
        conn.commit()

    previous_principal = main.app.dependency_overrides.get(require_phase4_principal)
    previous_domain = main.app.dependency_overrides.pop(require_phase4_domain_access, None)
    main.app.dependency_overrides[require_phase4_principal] = lambda: principal
    client = TestClient(main.app)
    try:
        own = client.post(
            "/api/v1/knowledge-runtime/feat-048/lifecycle",
            json={"knowledge_id": own_resource, "lifecycle_status": "DRAFT", "changed_by": subject},
            headers={"X-Trace-Id": trace_own},
        )
        # A 404 from the handler means the tenant authorization passed and the
        # route then correctly reported that this test fixture has no knowledge row.
        assert own.status_code == 404
        assert own.json()["detail"] == "knowledge item not found"

        foreign = client.post(
            "/api/v1/knowledge-runtime/feat-048/lifecycle",
            json={"knowledge_id": foreign_resource, "lifecycle_status": "DRAFT", "changed_by": subject},
            headers={"X-Trace-Id": trace_foreign},
        )
        assert foreign.status_code == 403
        assert foreign.json()["detail"]["reason_code"] == "resource_tenant_binding_missing_or_mismatched"
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT allowed,reason_code FROM kaizo_p14_audit_events
                       WHERE trace_id=%s ORDER BY occurred_at DESC LIMIT 1""",
                    (trace_foreign,),
                )
                audit = cur.fetchone()
        assert audit == (False, "resource_tenant_binding_missing_or_mismatched")
    finally:
        if previous_principal is None:
            main.app.dependency_overrides.pop(require_phase4_principal, None)
        else:
            main.app.dependency_overrides[require_phase4_principal] = previous_principal
        if previous_domain is not None:
            main.app.dependency_overrides[require_phase4_domain_access] = previous_domain
