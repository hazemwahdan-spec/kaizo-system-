from __future__ import annotations

from fastapi.testclient import TestClient

import main
import persistence
from productization import coach_assessment_workflow, coach_roster, product_api
from productization.identity import Principal


def _principal(actor: str, tenant: str) -> Principal:
    return Principal(
        actor_id=actor, role="coach", tenant_id=tenant,
        resource_owner_id=None, verified=True, source="oidc_jwt",
    permissions=frozenset({"product"}),
    )


def _setup(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_PERSISTENCE_MODE", "memory")
    monkeypatch.delenv("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", raising=False)
    coach_roster.reset_memory_state()
    coach_assessment_workflow.reset_memory_state()
    principals = {
        "coach-a": _principal("auth0|coach-a", "ACADEMY-A"),
        "coach-b": _principal("auth0|coach-b", "ACADEMY-A"),
        "coach-c": _principal("auth0|coach-c", "ACADEMY-B"),
    }

    def resolve(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise product_api.IdentityNotConfiguredError("Bearer authentication is required")
        token = authorization.removeprefix("Bearer ")
        if token not in principals:
            raise product_api.IdentityNotConfiguredError("unknown test token")
        return principals[token]

    monkeypatch.setattr(product_api, "resolve_bearer_principal", resolve)
    client = TestClient(main.app)
    headers_a = {"Authorization": "Bearer coach-a"}
    headers_b = {"Authorization": "Bearer coach-b"}
    headers_c = {"Authorization": "Bearer coach-c"}
    athlete_a = coach_roster.create_owned_athlete(
        tenant_id="ACADEMY-A", coach_actor_id="auth0|coach-a",
        display_name="Owned Athlete A",
    )
    athlete_b = coach_roster.create_owned_athlete(
        tenant_id="ACADEMY-A", coach_actor_id="auth0|coach-b",
        display_name="Owned Athlete B",
    )
    athlete_c = coach_roster.create_owned_athlete(
        tenant_id="ACADEMY-B", coach_actor_id="auth0|coach-c",
        display_name="Owned Athlete C",
    )
    return client, headers_a, headers_b, headers_c, athlete_a, athlete_b, athlete_c


def test_assessment_uses_verified_bearer_owner_and_scoped_readback(monkeypatch):
    c, ha, hb, hc, a, b, other_tenant = _setup(monkeypatch)
    forged_headers = {
        **ha,
        "X-KAIZO-Actor": "attacker",
        "X-KAIZO-Role": "administrator",
        "X-KAIZO-Tenant": "ACADEMY-B",
    }
    created = c.post(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments",
        headers=forged_headers,
        json={
            "template_id": "U15-GRIP-BASELINE",
            "measurements": {"grip_strength_kg": 18.5, "entry_quality": 7},
            "recorded_by": "forged-caller",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["recorded_by"] == "auth0|coach-a"
    assert body["athlete_id"] == a["athlete_id"]
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False

    readback = c.get(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments/{body['assessment_id']}",
        headers=ha,
    )
    assert readback.status_code == 200
    assert readback.json()["measurements"]["grip_strength_kg"] == 18.5

    assert c.get(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments/{body['assessment_id']}",
        headers=hb,
    ).status_code == 404
    assert c.get(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments/{body['assessment_id']}",
        headers=hc,
    ).status_code == 404
    assert c.get(
        f"/api/v1/product/coach/athletes/{b['athlete_id']}/assessments",
        headers=ha,
    ).status_code == 404
    assert c.get(
        f"/api/v1/product/coach/athletes/{other_tenant['athlete_id']}/assessments",
        headers=ha,
    ).status_code == 404


def test_kpi_definition_and_capture_are_coach_and_athlete_scoped(monkeypatch):
    c, ha, hb, hc, a, b, _ = _setup(monkeypatch)
    definition = c.post(
        "/api/v1/product/coach/kpi-definitions",
        headers=ha,
        json={
            "kpi_id": "GRIP-STRENGTH",
            "name": "Grip strength",
            "metric_name": "grip_strength",
            "unit": "kg",
            "target": 25.0,
            "direction": "higher_is_better",
            "defined_by": "forged-caller",
        },
    )
    assert definition.status_code == 201, definition.text
    assert definition.json()["coach_final_authority"] is True
    assert definition.json()["execution_authorized"] is False
    assert c.get(
        "/api/v1/product/coach/kpi-definitions/GRIP-STRENGTH", headers=hb
    ).status_code == 404

    assessment = c.post(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments",
        headers=ha,
        json={"template_id": "U15-GRIP", "measurements": {"grip_strength_kg": 18.5}},
    )
    assert assessment.status_code == 201, assessment.text
    capture = c.post(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/kpi-captures",
        headers=ha,
        json={
            "kpi_id": "GRIP-STRENGTH",
            "value": 18.5,
            "assessment_id": assessment.json()["assessment_id"],
            "captured_by": "forged-caller",
        },
    )
    assert capture.status_code == 201, capture.text
    assert capture.json()["captured_by"] == "auth0|coach-a"

    assert c.get(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/kpi-captures/{capture.json()['capture_id']}",
        headers=hb,
    ).status_code == 404
    assert c.post(
        f"/api/v1/product/coach/athletes/{b['athlete_id']}/kpi-captures",
        headers=ha,
        json={"kpi_id": "GRIP-STRENGTH", "value": 18.5},
    ).status_code == 404
    assert c.post(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/kpi-captures",
        headers=hc,
        json={"kpi_id": "GRIP-STRENGTH", "value": 18.5},
    ).status_code == 404


def test_evidence_attachment_and_snapshot_preserve_dependency_lineage(monkeypatch):
    c, ha, hb, _, a, b, _ = _setup(monkeypatch)
    assessment = c.post(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments",
        headers=ha,
        json={"template_id": "U15-BASELINE", "measurements": {"entry_quality": 7}},
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["assessment_id"]

    definition = c.post(
        "/api/v1/product/coach/kpi-definitions",
        headers=ha,
        json={
            "kpi_id": "ENTRY-QUALITY", "name": "Entry quality",
            "metric_name": "entry_quality", "unit": "score",
            "direction": "higher_is_better",
        },
    )
    assert definition.status_code == 201, definition.text
    capture = c.post(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/kpi-captures",
        headers=ha,
        json={"kpi_id": "ENTRY-QUALITY", "value": 7, "assessment_id": assessment_id},
    )
    assert capture.status_code == 201, capture.text

    coach_assessment_workflow._MEMORY_EVIDENCE["EVID-OWNED"] = {
        "evidence_id": "EVID-OWNED", "subject_type": "assessment",
        "subject_id": assessment_id,
    }
    attached = c.post(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments/{assessment_id}/evidence",
        headers=ha, json={"evidence_id": "EVID-OWNED"},
    )
    assert attached.status_code == 201, attached.text
    evidence_read = c.get(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments/{assessment_id}/evidence",
        headers=ha,
    )
    assert evidence_read.status_code == 200
    assert evidence_read.json()["attachments"][0]["evidence_id"] == "EVID-OWNED"
    assert c.get(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments/{assessment_id}/evidence",
        headers=hb,
    ).status_code == 404

    snapshot = c.post(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/state-snapshots",
        headers=ha,
        json={
            "assessment_id": assessment_id,
            "snapshot_type": "baseline",
            "kpi_capture_ids": [capture.json()["capture_id"]],
        },
    )
    assert snapshot.status_code == 201, snapshot.text
    assert snapshot.json()["measurements"]["entry_quality"] == 7
    assert snapshot.json()["kpis"][0]["value"] == 7
    readback = c.get(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/state-snapshots/{snapshot.json()['snapshot_id']}",
        headers=ha,
    )
    assert readback.status_code == 200
    assert readback.json()["assessment_id"] == assessment_id
    assert c.get(
        f"/api/v1/product/coach/athletes/{a['athlete_id']}/state-snapshots/{snapshot.json()['snapshot_id']}",
        headers=hb,
    ).status_code == 404
    assert c.post(
        f"/api/v1/product/coach/athletes/{b['athlete_id']}/state-snapshots",
        headers=ha,
        json={
            "assessment_id": assessment_id,
            "snapshot_type": "baseline",
            "kpi_capture_ids": [capture.json()["capture_id"]],
        },
    ).status_code == 404


def test_anonymous_invalid_and_duplicate_requests_fail_without_execution(monkeypatch):
    c, ha, _, _, a, _, _ = _setup(monkeypatch)
    path = f"/api/v1/product/coach/athletes/{a['athlete_id']}/assessments"
    valid = c.post(
        path, headers=ha,
        json={"template_id": "AUDIT-BASELINE", "measurements": {"score": 5}},
    )
    assert valid.status_code == 201, valid.text
    assert c.post(
        path, json={"template_id": "U15", "measurements": {"score": 1}}
    ).status_code == 401
    assert c.post(
        path, headers=ha, json={"template_id": "U15", "measurements": {}}
    ).status_code == 400

    bad_kpi = c.post(
        "/api/v1/product/coach/kpi-definitions",
        headers=ha,
        json={
            "kpi_id": "BAD", "name": "Bad", "metric_name": "bad",
            "unit": "x", "direction": "not-a-direction",
        },
    )
    assert bad_kpi.status_code == 400

    assert all(event["who"] == "auth0|coach-a" for event in coach_assessment_workflow._MEMORY_AUDIT)
    actions = [event["action"] for event in coach_assessment_workflow._MEMORY_AUDIT]
    assert "COACH_ASSESSMENT_RECORDED" in actions
    assert all(event["tenant_id"] == "ACADEMY-A" for event in coach_assessment_workflow._MEMORY_AUDIT)

def test_verified_coach_requires_postgres_for_product_and_state_cycle_routes(monkeypatch):
    c, ha, _hb, _hc, athlete, _b, _other_tenant = _setup(monkeypatch)
    # Simulate a valid OIDC principal while durable storage is unavailable.
    # Production must fail closed instead of silently using the memory adapter.
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: False)

    roster_read = c.get("/api/v1/product/coach/athletes", headers=ha)
    athlete_write = c.post(
        "/api/v1/product/coach/athletes",
        headers=ha,
        json={"display_name": "Must not be stored in memory"},
    )
    twin_read = c.get(
        f"/api/v1/state-cycle/feat-042/digital-twin-state/{athlete['athlete_id']}",
        headers=ha,
    )

    assert roster_read.status_code == 503, roster_read.text
    assert athlete_write.status_code == 503, athlete_write.text
    assert twin_read.status_code == 503, twin_read.text

