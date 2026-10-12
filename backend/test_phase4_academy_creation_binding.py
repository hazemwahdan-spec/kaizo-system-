"""PostgreSQL integration test for atomic academy creation + tenant binding."""
from uuid import uuid4

from fastapi.testclient import TestClient

import main
import persistence
from phase4_domain_authorization import require_phase4_domain_access
from phase4_identity_boundary import Principal, require_phase4_principal


def test_academy_create_persists_binding_in_same_transaction():
    suffix = uuid4().hex
    tenant_id = "academy-create-tenant-" + suffix
    subject = "oidc|academy-owner-" + suffix
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kaizo_tenants(tenant_id,display_name) VALUES (%s,%s)",
                (tenant_id, tenant_id),
            )
            cur.execute(
                """INSERT INTO kaizo_tenant_memberships(tenant_id,subject_id,role,status)
                   VALUES (%s,%s,'academy','ACTIVE')""",
                (tenant_id, subject),
            )
        conn.commit()

    principal = Principal(
        actor_id=subject, role="academy", tenant_id=tenant_id,
        resource_owner_id=None, verified=True, source="oidc_jwt",
    )
    previous_principal = main.app.dependency_overrides.get(require_phase4_principal)
    previous_domain = main.app.dependency_overrides.pop(require_phase4_domain_access, None)
    main.app.dependency_overrides[require_phase4_principal] = lambda: principal
    client = TestClient(main.app)
    try:
        response = client.post(
            "/api/v1/academy/academies",
            json={"name": "Academy " + suffix, "owner_id": subject,
                  "status": "ACTIVE", "coach_final_authority": True},
            headers={"X-Trace-Id": "academy-create-" + suffix},
        )
        assert response.status_code == 201, response.text
        academy_id = response.json()["academy_id"]
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT tenant_id,bound_by_subject FROM kaizo_resource_tenant_bindings
                       WHERE resource_type='academy' AND resource_id=%s""",
                    (academy_id,),
                )
                binding = cur.fetchone()
        assert binding == (tenant_id, subject)

        event_response = client.post(
            "/api/v1/competition/events",
            json={"event_name": "Event " + suffix, "date": "2026-11-12",
                  "context": {"level": "club"}, "created_by": subject,
                  "evidence_refs": [], "coach_final_authority": True},
            headers={"X-Trace-Id": "event-create-" + suffix},
        )
        assert event_response.status_code == 201, event_response.text
        event_id = event_response.json()["event_id"]
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT tenant_id,bound_by_subject FROM kaizo_resource_tenant_bindings
                       WHERE resource_type='competition_event' AND resource_id=%s""",
                    (event_id,),
                )
                event_binding = cur.fetchone()
        assert event_binding == (tenant_id, subject)

        knowledge_id = "knowledge-" + suffix
        knowledge_response = client.post(
            "/api/v1/knowledge-runtime/feat-047/provenance",
            json={"knowledge_id": knowledge_id, "source_type": "IJF",
                  "source_ref": "https://example.invalid/technical-source",
                  "source_version": "v1", "evidence_status": "VERIFIED",
                  "provenance_note": "Phase 4 tenant binding integration test",
                  "evidence_refs": ["P4-TEST-SOURCE"], "changed_by": subject,
                  "coach_final_authority": True},
            headers={"X-Trace-Id": "knowledge-create-" + suffix},
        )
        assert knowledge_response.status_code == 201, knowledge_response.text
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT tenant_id,bound_by_subject FROM kaizo_resource_tenant_bindings
                       WHERE resource_type='knowledge' AND resource_id=%s""",
                    (knowledge_id,),
                )
                knowledge_binding = cur.fetchone()
        assert knowledge_binding == (tenant_id, subject)
    finally:
        if previous_principal is None:
            main.app.dependency_overrides.pop(require_phase4_principal, None)
        else:
            main.app.dependency_overrides[require_phase4_principal] = previous_principal
        if previous_domain is not None:
            main.app.dependency_overrides[require_phase4_domain_access] = previous_domain
