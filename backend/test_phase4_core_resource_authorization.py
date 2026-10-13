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
        "test_actual_route_auth_denial_is_durably_audited",
    }:
        monkeypatch.setattr(authz, "_audit_authorization", lambda **_: None)



def _ensure_audit_tenant():
    with main.persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kaizo_tenants (tenant_id, display_name, status) "
                "VALUES ('academy-a', 'Phase 4 route-test academy', 'active') "
                "ON CONFLICT (tenant_id) DO NOTHING"
            )
        conn.commit()


def test_authorization_decisions_are_durably_audited():
    _ensure_audit_tenant()
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


def test_actual_route_auth_denial_is_durably_audited(monkeypatch):
    _ensure_audit_tenant()
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: False)
    correlation_id = "phase4-route-auth-denial"
    response = client.get(
        "/api/v1/athletes/no-membership",
        headers={
            "Authorization": "Bearer signed-test-token",
            "X-Correlation-ID": correlation_id,
        },
    )
    assert response.status_code == 403
    from phase4_identity_store import list_authorization_audit
    rows = list_authorization_audit(correlation_id=correlation_id)
    assert any(
        row["decision"] == "deny"
        and row["reason_code"] == "ACTIVE_MEMBERSHIP_REQUIRED"
        and row["request_route"] == "/api/v1/athletes/no-membership"
        for row in rows
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


def test_actual_create_assessment_denies_minor_without_active_consent_before_read_or_write(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(authz, "get_resource_tenant", lambda **_: "academy-a")
    monkeypatch.setattr(authz, "get_verified_age_classification", lambda **_: "minor")
    monkeypatch.setattr(authz, "get_active_minor_consent_id", lambda **_: None)
    reads, writes = [], []
    monkeypatch.setattr(main.persistence, "get_athlete", lambda athlete_id: reads.append(athlete_id) or {"athlete_id": athlete_id})
    monkeypatch.setattr(main.persistence, "upsert_assessment", lambda item: writes.append(item))
    response = client.post(
        "/api/v1/assessments",
        json={"athlete_id": "minor-athlete", "template_id": "TPL", "measurements": {"x": 1}, "recorded_by": "coach"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert "guardian consent" in response.text.lower()
    assert reads == []
    assert writes == []


def test_actual_get_athlete_denies_missing_verified_age_classification(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(authz, "get_resource_tenant", lambda **_: "academy-a")
    monkeypatch.setattr(authz, "get_verified_age_classification", lambda **_: None)
    reads = []
    monkeypatch.setattr(main.persistence, "get_athlete", lambda athlete_id: reads.append(athlete_id) or {"athlete_id": athlete_id})
    response = client.get(
        "/api/v1/athletes/athlete-without-age-classification",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert "age classification" in response.text.lower()
    assert reads == []


def test_actual_problem_read_denies_cross_tenant_before_problem_read(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(authz, "get_resource_tenant", lambda **_: "academy-b")
    reads = []
    monkeypatch.setattr(
        main.persistence, "get_problem_statement",
        lambda problem_id: reads.append(problem_id) or {"problem_id": problem_id, "athlete_id": "foreign-athlete"},
    )
    response = client.get(
        "/api/v1/problem-statements/problem-from-other-academy",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert reads == []


def test_actual_decision_candidate_read_denies_cross_tenant_before_candidate_read(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(authz, "get_resource_tenant", lambda **_: "academy-b")
    reads = []
    monkeypatch.setattr(
        main.persistence, "get_decision_candidate",
        lambda candidate_id: reads.append(candidate_id) or {"candidate_id": candidate_id, "athlete_id": "foreign-athlete"},
    )
    response = client.get(
        "/api/v1/decision-candidates/foreign-candidate/rationale",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert reads == []


def test_actual_training_plan_read_denies_cross_tenant_before_plan_read(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(authz, "get_resource_tenant", lambda **_: "academy-b")
    reads = []
    monkeypatch.setattr(
        main.persistence, "get_training_plan",
        lambda plan_id: reads.append(plan_id) or {"plan_id": plan_id, "athlete_id": "foreign-athlete"},
    )
    response = client.get(
        "/api/v1/training-plans/foreign-plan",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert reads == []


def test_actual_digital_twin_denies_unmapped_case_before_write(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(
        authz, "get_resource_tenant",
        lambda **kwargs: "academy-a" if kwargs.get("resource_id") == "athlete-a" else None,
    )
    monkeypatch.setattr(authz, "get_verified_age_classification", lambda **_: "adult")
    monkeypatch.setattr(
        main, "get_resource_tenant",
        lambda **kwargs: "academy-a" if kwargs.get("resource_id") == "athlete-a" else None,
    )
    writes = []
    monkeypatch.setattr(main.persistence, "upsert_digital_twin", lambda state: writes.append(state))
    response = client.post(
        "/api/v1/digital-twin/sync",
        json={
            "case_id": "case-without-authoritative-owner",
            "entity_id": "athlete-a",
            "state": {"score": 4},
            "source_event": "PHASE4_TEST",
            "coach_final_authority": True,
        },
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert writes == []


def test_actual_audit_log_endpoint_reads_only_the_authenticated_academy(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    scoped_rows = [{
        "timestamp": "2026-10-13T00:00:00+00:00",
        "who": "oidc|phase4-test-coach",
        "actor_role": "coach",
        "resource_type": "athlete",
        "resource_id": "athlete-a",
        "action": "read",
        "decision": "deny",
        "reason_code": "RESOURCE_TENANT_SCOPE_DENIED",
        "consent_id": None,
        "policy_version": "phase4-core-v1",
        "correlation_id": "audit-tenant-test",
        "request_route": "/api/v1/athletes/{athlete_id}",
    }]
    monkeypatch.setattr(main, "list_authorization_audit_for_academy", lambda **kwargs: scoped_rows)
    monkeypatch.setattr(main.persistence, "list_audit_logs", lambda: (_ for _ in ()).throw(AssertionError("global audit log must not be read")))
    response = client.get(
        "/api/v1/audit/logs",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 200
    logs = response.json()["logs"]
    assert len(logs) == 1
    assert logs[0]["action"] == "AUTHORIZATION_DENY"
    assert logs[0]["new_value"]["correlation_id"] == "audit-tenant-test"


def test_mounted_knowledge_route_fails_closed_without_resource_scope(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    response = client.post(
        "/api/v1/knowledge-runtime/feat-049/retrieve",
        json={"workflow_context": "coach_review", "query": "cross-academy data must not be returned", "requested_by": "coach-1"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 503
    assert "No approved tenant/resource scope policy" in response.json()["detail"]


def test_core_routes_fail_closed_when_oidc_gate_is_disabled(monkeypatch):
    monkeypatch.delenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", raising=False)
    response = client.get("/api/v1/athletes/any-id")
    assert response.status_code == 503



def test_generated_feature_create_fails_closed_until_feature_record_scope_policy_exists(monkeypatch):
    """An arbitrary nested athlete_id must not authorize a feature-record write."""
    import backend.feature_runtime as feature_runtime

    principal = _principal()
    main.app.dependency_overrides[authz.require_core_actor] = lambda: principal
    audit_events = []
    monkeypatch.setattr(
        authz, "_audit_authorization",
        lambda **kwargs: audit_events.append(kwargs),
    )
    writes = []
    monkeypatch.setattr(
        feature_runtime, "_create",
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )
    try:
        response = client.post(
            "/api/v1/features/feat-071/athlete-progress-report",
            json={
                "subject_id": "unbound-subject",
                "actor_id": "caller-supplied-actor",
                "payload": {
                    "athlete_id": "same-academy-athlete",
                    "period": "2026-10",
                    "progress": {"state": "STABLE"},
                },
                "evidence_refs": [],
                "coach_final_authority": True,
                "execution_authorized": False,
            },
            headers={"Authorization": "Bearer signed-test-token", "X-Correlation-ID": "phase4-feature-scope-deny"},
        )
    finally:
        main.app.dependency_overrides.pop(authz.require_core_actor, None)

    assert response.status_code == 503
    assert writes == []
    assert any(
        item.get("resource_type") == "feature_record"
        and item.get("decision") == "deny"
        and item.get("reason_code") == "RESOURCE_SCOPE_POLICY_NOT_CONFIGURED"
        and item.get("correlation_id") == "phase4-feature-scope-deny"
        for item in audit_events
    )


def test_mounted_route_cannot_use_ignored_extra_field_as_resource_proof(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    writes = []
    monkeypatch.setattr(main.persistence, "append_audit", lambda **kwargs: writes.append(kwargs))
    response = client.post(
        "/api/v1/audit-trace/feat-052/trace",
        json={
            "actor_id": "caller-controlled-actor",
            "action": "test",
            "athlete_id": "athlete-in-same-tenant-but-not-bound-to-this-route",
        },
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 503
    assert writes == []


def test_mounted_route_denies_partial_scope_when_another_identifier_is_unmapped(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "MOUNTED_ROUTE_SCOPE_POLICIES", {
        ("POST", "/api/v1/competition/readiness"): {
            "roles": ("coach",),
            "required_bindings": {},
            "consent_resource": "competition_readiness",
            "consent_action": "write",
        }
    })
    response = client.post(
        "/api/v1/competition/readiness",
        json={
            "athlete_id": "athlete-in-academy-a",
            "event_id": "event-without-approved-scope",
            "indicators": {"grip": 0.7},
            "assessed_by": "coach-a",
        },
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 503
    assert "event_id" in response.json()["detail"]


def test_declared_body_model_ignores_extra_resource_id(monkeypatch):
    import backend.audit_trace_runtime as audit_runtime
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "MOUNTED_ROUTE_SCOPE_POLICIES", {
        ("POST", "/api/v1/audit-trace/feat-052/trace"): {
            "roles": ("coach",), "required_bindings": {},
            "consent_resource": "audit_trace", "consent_action": "write",
        }
    })
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda resource_type, resource_id: resource_id)
    monkeypatch.setattr(main, "assert_minor_consent", lambda **_: None)
    writes = []
    monkeypatch.setattr(audit_runtime, "save_trace", lambda record: writes.append(record))
    response = client.post(
        "/api/v1/audit-trace/feat-052/trace",
        json={"actor_id": "header-actor", "action": "test", "athlete_id": "extra-only"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 503
    assert writes == []


def test_explicit_training_workflow_read_policy_checks_tenant_and_consent(monkeypatch):
    import backend.training_workflow as training
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda resource_type, resource_id: resource_id)
    checked = []
    monkeypatch.setattr(main, "assert_minor_consent", lambda **kw: checked.append(kw))
    monkeypatch.setattr(training, "_list", lambda feature, athlete_id: [])
    response = client.get(
        "/api/v1/training-workflow/athletes/athlete-a",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 200
    assert response.json()["athlete_id"] == "athlete-a"
    assert checked and checked[0]["resource"] == "training_workflow"
    assert checked[0]["action"] == "read"


def test_explicit_training_workflow_read_policy_rejects_parent_role(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal(role="parent"))
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    reads = []
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda resource_type, resource_id: reads.append(resource_id))
    response = client.get(
        "/api/v1/training-workflow/athletes/athlete-a",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert reads == []


def test_explicit_decision_state_link_read_policy_checks_decision_owner_and_consent(monkeypatch):
    import backend.state_cycle as state_cycle
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda resource_type, resource_id: "athlete-a")
    checked = []
    monkeypatch.setattr(main, "assert_minor_consent", lambda **kw: checked.append(kw))
    monkeypatch.setattr(state_cycle, "_latest_link", lambda decision_id: {"decision_id": decision_id})
    response = client.get(
        "/api/v1/state-cycle/feat-044/decision-state-link/decision-a",
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 404
    assert checked and checked[0]["resource"] == "decision_record"
    assert checked[0]["action"] == "read"


def test_next_state_policy_checks_body_athlete_and_actor(monkeypatch):
    import state_cycle
    principal = Principal(actor_id="coach-1", role="coach", tenant_id="academy-a", resource_owner_id=None, verified=True, source="oidc_jwt")
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda resource_type, resource_id: resource_id)
    checked = []
    monkeypatch.setattr(main, "assert_minor_consent", lambda **kw: checked.append(kw))
    monkeypatch.setattr(state_cycle, "_get_state", lambda athlete_id: None)
    response = client.post(
        "/api/v1/state-cycle/feat-045/next-state",
        json={"athlete_id": "athlete-a", "requested_by": "coach-1"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 404
    assert checked and checked[0]["resource"] == "digital_twin_state"
    assert checked[0]["action"] == "read"


def test_next_state_policy_denies_actor_mismatch(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    checks = []
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **kw: checks.append(kw))
    response = client.post(
        "/api/v1/state-cycle/feat-045/next-state",
        json={"athlete_id": "athlete-a", "requested_by": "wrong-actor"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert checks == []


def test_decision_state_link_write_requires_same_athlete_and_authenticated_actor(monkeypatch):
    import state_cycle
    principal = Principal(actor_id="coach-1", role="coach", tenant_id="academy-a", resource_owner_id=None, verified=True, source="oidc_jwt")
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda resource_type, resource_id: "athlete-a")
    checked = []
    monkeypatch.setattr(main, "assert_minor_consent", lambda **kw: checked.append(kw))
    monkeypatch.setattr(state_cycle.persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(state_cycle.persistence, "get_decision_record", lambda decision_id: {"decision_id": decision_id, "athlete_id": "athlete-a"})
    monkeypatch.setattr(state_cycle.persistence, "append_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(state_cycle, "_get_state", lambda entity_id: {"version": 2})
    writes = []
    monkeypatch.setattr(state_cycle, "_save_link", lambda record: writes.append(record))
    response = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={"decision_id": "decision-a", "entity_id": "athlete-a", "state_version": 2, "state_ref": "athlete-a:v2", "linked_by": "coach-1"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 201
    assert writes and writes[0]["decision_id"] == "decision-a"
    assert any(item["resource"] == "decision_state_link" and item["action"] == "write" for item in checked)
    assert any(item["resource"] == "decision_record" and item["action"] == "read" for item in checked)


def test_decision_state_link_write_denies_cross_athlete_decision(monkeypatch):
    import state_cycle
    principal = Principal(actor_id="coach-1", role="coach", tenant_id="academy-a", resource_owner_id=None, verified=True, source="oidc_jwt")
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda resource_type, resource_id: "athlete-a")
    monkeypatch.setattr(main, "assert_minor_consent", lambda **kw: None)
    monkeypatch.setattr(state_cycle.persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(state_cycle.persistence, "get_decision_record", lambda decision_id: {"decision_id": decision_id, "athlete_id": "athlete-b"})
    monkeypatch.setattr(state_cycle.persistence, "append_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(state_cycle, "_get_state", lambda entity_id: {"version": 2})
    writes = []
    monkeypatch.setattr(state_cycle, "_save_link", lambda record: writes.append(record))
    response = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={"decision_id": "decision-b", "entity_id": "athlete-a", "state_version": 2, "state_ref": "athlete-a:v2", "linked_by": "coach-1"},
        headers={"Authorization": "Bearer signed-test-token"},
    )
    assert response.status_code == 403
    assert writes == []


def test_digital_twin_write_requires_case_and_evidence_scope(monkeypatch):
    import state_cycle
    principal = Principal(actor_id="coach-1", role="coach", tenant_id="academy-a", resource_owner_id=None, verified=True, source="oidc_jwt")
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda *args: "athlete-a")
    monkeypatch.setattr(main, "_assert_case_scope", lambda *args, **kwargs: "athlete-a")
    checked = []
    monkeypatch.setattr(main, "assert_minor_consent", lambda **kw: checked.append(kw))
    monkeypatch.setattr(state_cycle.persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(state_cycle.persistence, "append_audit", lambda *args, **kwargs: None)
    writes = []
    monkeypatch.setattr(state_cycle, "_get_state", lambda entity_id: None)
    monkeypatch.setattr(state_cycle, "_save_state", lambda record: writes.append(record))
    monkeypatch.setattr(state_cycle, "_save_history", lambda record: None)
    response = client.post("/api/v1/state-cycle/feat-042/digital-twin-state", json={"entity_id":"athlete-a","state":{"score":6},"source_event":"test","case_id":"case-a","updated_by":"coach-1","evidence_refs":["evidence-a"]}, headers={"Authorization":"Bearer signed-test-token"})
    assert response.status_code == 201
    assert writes
    assert any(x["resource"] == "evidence" and x["action"] == "read" for x in checked)


def test_digital_twin_write_denies_case_owned_by_different_athlete(monkeypatch):
    import state_cycle
    principal = Principal(actor_id="coach-1", role="coach", tenant_id="academy-a", resource_owner_id=None, verified=True, source="oidc_jwt")
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda *args: "athlete-a")
    monkeypatch.setattr(main, "_assert_case_scope", lambda *args, **kwargs: "athlete-b")
    monkeypatch.setattr(main, "assert_minor_consent", lambda **kw: None)
    monkeypatch.setattr(state_cycle.persistence, "is_postgres_enabled", lambda: True)
    writes = []
    monkeypatch.setattr(state_cycle, "_save_state", lambda record: writes.append(record))
    response = client.post("/api/v1/state-cycle/feat-042/digital-twin-state", json={"entity_id":"athlete-a","state":{"score":6},"source_event":"test","case_id":"case-b","updated_by":"coach-1","evidence_refs":["evidence-a"]}, headers={"Authorization":"Bearer signed-test-token"})
    assert response.status_code == 403
    assert writes == []


def test_training_progress_write_checks_actor_evidence_and_consent(monkeypatch):
    import training_workflow
    principal = Principal(actor_id="coach-1", role="coach", tenant_id="academy-a", resource_owner_id=None, verified=True, source="oidc_jwt")
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **_: None)
    monkeypatch.setattr(main, "_resolve_athlete_id", lambda *args: "athlete-a")
    checked = []
    monkeypatch.setattr(main, "assert_minor_consent", lambda **kw: checked.append(kw))
    monkeypatch.setattr(training_workflow, "_save", lambda *args, **kwargs: {"record_id": "record-a", "athlete_id": "athlete-a"})
    response = client.post("/api/v1/training-workflow/feat-039/progress-state", json={"athlete_id":"athlete-a","state":{"score":5},"evidence_refs":["evidence-a"],"updated_by":"coach-1"}, headers={"Authorization":"Bearer signed-test-token"})
    assert response.status_code == 201
    assert any(x["resource"] == "training_workflow" and x["action"] == "write" for x in checked)
    assert any(x["resource"] == "evidence" and x["action"] == "read" for x in checked)


def test_training_progress_write_denies_spoofed_updated_by(monkeypatch):
    principal = Principal(actor_id="coach-1", role="coach", tenant_id="academy-a", resource_owner_id=None, verified=True, source="oidc_jwt")
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    checks = []
    monkeypatch.setattr(main, "assert_resource_tenant", lambda **kw: checks.append(kw))
    response = client.post("/api/v1/training-workflow/feat-039/progress-state", json={"athlete_id":"athlete-a","state":{"score":5},"evidence_refs":["evidence-a"],"updated_by":"another-coach"}, headers={"Authorization":"Bearer signed-test-token"})
    assert response.status_code == 403
    assert checks == []


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            "/api/v1/knowledge-runtime/feat-047/provenance",
            {
                "knowledge_id": "phase4-unmapped-knowledge-test",
                "source_type": "test",
                "source_ref": "synthetic://phase4-unmapped",
                "source_version": "1",
                "evidence_status": "UNVERIFIED",
                "provenance_note": "synthetic fail-closed authorization regression",
                "evidence_refs": ["synthetic-evidence"],
                "changed_by": "oidc|phase4-test-coach",
                "coach_final_authority": True,
            },
        ),
        (
            "post",
            "/api/v1/reporting/export",
            {
                "academy_id": "academy-a",
                "requested_by": "oidc|phase4-test-coach",
                "report_type": "synthetic",
            },
        ),
    ],
)
def test_unmapped_mounted_routes_fail_closed_before_handler_write(
    monkeypatch, method, path, payload
):
    """A valid identity/body must not bypass missing route-specific scope policy."""
    import knowledge_runtime

    principal = _principal()
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)
    sentinel = "phase4-unmapped-knowledge-test"
    knowledge_runtime.MEMORY_ITEMS.pop(sentinel, None)

    response = getattr(client, method)(
        path,
        json=payload,
        headers={"Authorization": "Bearer signed-test-token"},
    )

    assert response.status_code == 503
    assert "No approved" in response.json()["detail"] or "policy" in response.json()["detail"].lower()
    assert sentinel not in knowledge_runtime.MEMORY_ITEMS


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/knowledge-runtime/feat-048/lifecycle"),
        ("post", "/api/v1/knowledge-runtime/feat-049/retrieve"),
        ("post", "/api/v1/knowledge-runtime/feat-050/link"),
        ("post", "/api/v1/evidence-safety/feat-057/evidence-quality"),
        ("post", "/api/v1/evidence-safety/feat-058/provenance"),
        ("post", "/api/v1/evidence-safety/feat-059/block"),
        ("post", "/api/v1/evidence-safety/feat-060/escalate"),
        ("post", "/api/v1/reporting/academy-dashboard"),
        ("post", "/api/v1/reporting/coach-summary"),
        ("get", "/api/v1/reporting/export/report-phase4-unmapped"),
        ("post", "/api/v1/reporting/kpi-trend"),
        ("post", "/api/v1/reporting/progress"),
    ],
)
def test_remaining_unmapped_mounted_route_families_remain_default_deny(
    monkeypatch, method, path
):
    """Routes without an approved route-specific policy cannot reach handlers."""
    principal = _principal()
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(authz, "has_active_membership", lambda **_: True)

    response = getattr(client, method)(
        path,
        json={} if method == "post" else None,
        headers={"Authorization": "Bearer signed-test-token"},
    )

    assert response.status_code == 503
    assert "policy" in response.json()["detail"].lower()
