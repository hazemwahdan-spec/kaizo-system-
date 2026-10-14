"""PostgreSQL integration test for atomic academy creation + tenant binding."""
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import persistence
import phase4_route_guard
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
        forged_owner = client.post(
            "/api/v1/academy/academies",
            json={"name": "Forged Academy " + suffix, "owner_id": "untrusted-owner",
                  "status": "ACTIVE", "coach_final_authority": True},
            headers={"X-Trace-Id": "academy-owner-spoof-" + suffix},
        )
        assert forged_owner.status_code == 403
        assert forged_owner.json()["detail"]["reason_code"] == "academy_owner_identity_mismatch"

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

        with patch.object(phase4_route_guard, "require_phase4_principal", return_value=principal):
            athlete_response = client.post(
                "/api/v1/athletes",
                json={"display_name": "Athlete " + suffix,
                      "metadata": {"date_of_birth": "2000-01-01"}},
                headers={"X-Trace-Id": "athlete-create-" + suffix},
            )
        assert athlete_response.status_code == 201, athlete_response.text
        athlete_id = athlete_response.json()["athlete_id"]
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT tenant_id,bound_by_subject FROM kaizo_resource_tenant_bindings
                       WHERE resource_type='athlete' AND resource_id=%s""",
                    (athlete_id,),
                )
                athlete_binding = cur.fetchone()
        assert athlete_binding == (tenant_id, subject)

        kpi_id = "KPI-TENANT-" + suffix
        kpi_response = client.post(
            "/api/v1/kpis",
            json={"kpi_id": kpi_id, "name": "Tenant KPI " + suffix,
                  "metric_name": "entry_timing_score", "unit": "score",
                  "target": 7, "direction": "higher_is_better",
                  "defined_by": subject},
            headers={"X-Trace-Id": "kpi-create-" + suffix},
        )
        assert kpi_response.status_code == 201, kpi_response.text
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT tenant_id,bound_by_subject FROM kaizo_resource_tenant_bindings
                       WHERE resource_type='kpi_definition' AND resource_id=%s""",
                    (kpi_id,),
                )
                kpi_binding = cur.fetchone()
        assert kpi_binding == (tenant_id, subject)
        kpi_read = client.get(f"/api/v1/kpis/{kpi_id}")
        assert kpi_read.status_code == 200, kpi_read.text

        # FEAT-029 must reference persisted evidence. Seed an isolated, verified
        # fixture rather than relying on a global evidence ID that may not exist
        # in the disposable PostgreSQL database.
        feature_evidence_id = "P4-FEATURE-EVIDENCE-" + suffix
        persistence.upsert_evidence({
            "evidence_id": feature_evidence_id,
            "subject_type": "feature_rule",
            "subject_id": subject,
            "evidence_level": "E2",
            "status": "VERIFIED",
            "source_ref": "test-fixture://phase4-academy-binding",
            "claim": "Verified fixture evidence for tenant-binding integration test",
            "observed_value": {"test_fixture": True, "tenant_id": tenant_id},
            "verified_by": subject,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "notes": "Disposable PostgreSQL integration-test fixture only",
        })
        feature_response = client.post(
            "/api/v1/features/feat-029/progression-regression-rules",
            json={
                "subject_id": subject, "actor_id": subject,
                "payload": {"metric": "technical_quality", "threshold": 8,
                            "action": "PROGRESS", "adjustment": 1,
                            "rule_version": "1.0.0", "approval_status": "APPROVED"},
                "evidence_refs": [feature_evidence_id],
                "coach_final_authority": True, "execution_authorized": False,
            },
            headers={"X-Trace-Id": "feature-record-create-" + suffix},
        )
        assert feature_response.status_code == 201, feature_response.text
        feature_record_id = feature_response.json()["record_id"]
        feature_list = client.get("/api/v1/features/feat-029/progression-regression-rules")
        assert feature_list.status_code == 200, feature_list.text
        assert any(item["record_id"] == feature_record_id for item in feature_list.json()["records"])
        feature_read = client.get(
            f"/api/v1/features/feat-029/progression-regression-rules/{feature_record_id}"
        )
        assert feature_read.status_code == 200, feature_read.text

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

        ingested_id = "PRB-TENANT-PRIVATE-" + suffix
        ingest_response = client.post(
            "/api/v1/knowledge/ingest",
            json={"item_id": ingested_id, "domain": "problem",
                  "title": "TENANT-PRIVATE-SECRET-" + suffix,
                  "content": {"source": "tenant-private"}, "user_id": subject},
            headers={"X-Trace-Id": "knowledge-ingest-" + suffix},
        )
        assert ingest_response.status_code == 201, ingest_response.text
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT tenant_id,bound_by_subject FROM kaizo_resource_tenant_bindings
                       WHERE resource_type='knowledge_ingest' AND resource_id=%s""",
                    (ingested_id,),
                )
                ingested_binding = cur.fetchone()
        assert ingested_binding == (tenant_id, subject)
        public_library = client.get(
            "/api/v1/problem-library",
            params={"query": "TENANT-PRIVATE-SECRET-" + suffix},
        )
        assert public_library.status_code == 200
        assert public_library.json()["items"] == []

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
        previous_override = main.app.dependency_overrides.get(require_phase4_principal)
        main.app.dependency_overrides[require_phase4_principal] = lambda: Principal(
            actor_id=foreign_subject, role="academy", tenant_id=foreign_tenant,
            resource_owner_id=None, verified=True, source="oidc_jwt",
        )
        try:
            foreign_read = client.get(
                f"/api/v1/features/feat-029/progression-regression-rules/{feature_record_id}"
            )
        finally:
            if previous_override is None:
                main.app.dependency_overrides.pop(require_phase4_principal, None)
            else:
                main.app.dependency_overrides[require_phase4_principal] = previous_override
        assert foreign_read.status_code == 403
        assert foreign_read.json()["detail"]["reason_code"] == "resource_tenant_binding_missing_or_mismatched"

        foreign_kpi_id = "KPI-FOREIGN-" + suffix
        foreign_kpi = {
            "kpi_id": foreign_kpi_id, "name": "Foreign KPI " + suffix,
            "metric_name": "entry_timing_score", "unit": "score", "target": 7,
            "direction": "higher_is_better", "defined_by": foreign_subject,
            "status": "ACTIVE", "created_at": "2026-10-13T00:00:00+00:00",
            "updated_at": "2026-10-13T00:00:00+00:00",
        }
        persistence.upsert_kpi_definition(
            foreign_kpi, tenant_id=foreign_tenant, bound_by_subject=foreign_subject,
        )
        from pytest import raises
        cross_tenant_capture_id = "capture-cross-tenant-" + suffix
        with raises(persistence.PersistenceConfigurationError):
            persistence.upsert_kpi_capture(
                {
                    "capture_id": cross_tenant_capture_id, "athlete_id": athlete_id,
                    "kpi_id": foreign_kpi_id, "value": 5.2, "captured_by": subject,
                    "assessment_id": None, "captured_at": "2026-10-13T00:00:00+00:00",
                    "created_at": "2026-10-13T00:00:00+00:00",
                },
                tenant_id=tenant_id, bound_by_subject=subject, role="academy",
                trace_id="cross-tenant-kpi-" + suffix,
            )
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM kaizo_kpi_captures WHERE capture_id=%s",
                    (cross_tenant_capture_id,),
                )
                assert cur.fetchone() is None

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
