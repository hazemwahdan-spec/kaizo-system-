"""PostgreSQL integration test for atomic academy creation + tenant binding."""
from uuid import uuid4

from fastapi.testclient import TestClient

import main
import persistence
from phase4_domain_authorization import require_phase4_domain_access
from phase4_identity_boundary import Principal, require_phase4_principal


def test_academy_create_persists_binding_in_same_transaction():
    persistence.initialize()
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

        group_response = client.post(
            "/api/v1/academy/groups",
            json={"academy_id": academy_id, "name": "Group " + suffix,
                  "coach_final_authority": True},
            headers={"X-Trace-Id": "group-create-" + suffix},
        )
        assert group_response.status_code == 201, group_response.text
        group_id = group_response.json()["group_id"]
        membership_response = client.post(
            "/api/v1/academy/memberships",
            json={"academy_id": academy_id, "coach_id": "coach-target-" + suffix,
                  "role": "COACH", "coach_final_authority": True},
            headers={"X-Trace-Id": "membership-create-" + suffix},
        )
        assert membership_response.status_code == 201, membership_response.text
        membership_id = membership_response.json()["membership_id"]
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT resource_type,tenant_id,bound_by_subject FROM kaizo_resource_tenant_bindings
                       WHERE (resource_type,resource_id) IN (('academy_group',%s),('academy_membership',%s))
                       ORDER BY resource_type""",
                    (group_id, membership_id),
                )
                child_bindings = cur.fetchall()
        assert child_bindings == [
            ("academy_group", tenant_id, subject),
            ("academy_membership", tenant_id, subject),
        ]

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

        legacy_id = "legacy-knowledge-" + suffix
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO kaizo_knowledge_repository(item_id,payload,updated_at)
                       VALUES (%s,%s::jsonb,%s)""",
                    (legacy_id, '{"knowledge_id":"'+legacy_id+'","lifecycle_status":"DRAFT"}', "2026-10-13T00:00:00+00:00"),
                )
            conn.commit()
        legacy_response = client.post(
            "/api/v1/knowledge-runtime/feat-047/provenance",
            json={"knowledge_id": legacy_id, "source_type": "IJF",
                  "source_ref": "P4-LEGACY-UNBOUND", "source_version": "v1",
                  "evidence_status": "VERIFIED", "provenance_note": "Must not be auto-claimed",
                  "evidence_refs": ["P4-LEGACY"], "changed_by": subject,
                  "coach_final_authority": True},
            headers={"X-Trace-Id": "legacy-knowledge-" + suffix},
        )
        assert legacy_response.status_code == 403
        assert legacy_response.json()["detail"]["reason_code"] == "resource_tenant_binding_missing_or_mismatched"
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_resource_tenant_bindings
                       WHERE resource_type='knowledge' AND resource_id=%s""",
                    (legacy_id,),
                )
                assert cur.fetchone() is None

        foreign_tenant = "foreign-knowledge-tenant-" + suffix
        foreign_subject = "oidc|foreign-academy-" + suffix
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO kaizo_tenants(tenant_id,display_name) VALUES (%s,%s)",
                    (foreign_tenant, foreign_tenant),
                )
                cur.execute(
                    """INSERT INTO kaizo_tenant_memberships(tenant_id,subject_id,role,status)
                       VALUES (%s,%s,'academy','ACTIVE')""",
                    (foreign_tenant, foreign_subject),
                )
            conn.commit()
        foreign_knowledge_id = "foreign-knowledge-" + suffix
        foreign_payload = {
            "knowledge_id": foreign_knowledge_id, "source_type": "IJF",
            "source_ref": "FOREIGN-TENANT-ONLY-SOURCE",
            "source_version": "v1", "evidence_status": "VERIFIED",
            "provenance_note": "FOREIGN-TENANT-ONLY-TOKEN",
            "lifecycle_status": "APPROVED", "changed_by": foreign_subject,
            "created_at": "2026-10-13T00:00:00+00:00",
            "updated_at": "2026-10-13T00:00:00+00:00",
        }
        persistence.upsert_knowledge(
            foreign_knowledge_id, foreign_payload, foreign_payload["updated_at"],
            tenant_id=foreign_tenant, bound_by_subject=foreign_subject,
        )
        retrieval = client.post(
            "/api/v1/knowledge-runtime/feat-049/retrieve",
            json={"workflow_context": "tenant isolation regression",
                  "query": "FOREIGN-TENANT-ONLY-TOKEN", "requested_by": subject,
                  "coach_final_authority": True},
            headers={"X-Trace-Id": "tenant-retrieval-" + suffix},
        )
        assert retrieval.status_code == 200, retrieval.text
        assert retrieval.json()["results"] == []
    finally:
        if previous_principal is None:
            main.app.dependency_overrides.pop(require_phase4_principal, None)
        else:
            main.app.dependency_overrides[require_phase4_principal] = previous_principal
        if previous_domain is not None:
            main.app.dependency_overrides[require_phase4_domain_access] = previous_domain
