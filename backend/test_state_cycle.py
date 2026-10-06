import os
os.environ["KAIZO_PERSISTENCE_MODE"] = "memory"

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _update(entity_id: str, state: dict, expected_version=None):
    payload = {
        "entity_id": entity_id,
        "state": state,
        "source_event": "FEAT-040_NEXT_DECISION",
        "case_id": "CASE-001",
        "updated_by": "coach-1",
        "evidence_refs": ["EVID-001"],
        "coach_final_authority": True,
    }
    if expected_version is not None:
        payload["expected_version"] = expected_version
    return client.post("/api/v1/state-cycle/feat-042/digital-twin-state", json=payload)


def test_feat_042_to_045_real_state_cycle():
    entity = "athlete-integration-1"

    first = _update(entity, {"progress_state": "IMPROVING", "kpi": 6})
    assert first.status_code == 201
    body = first.json()
    assert body["state"]["version"] == 1
    assert body["history"]["version"] == 1
    assert body["state"]["coach_final_authority"] is True
    assert body["state"]["execution_authorized"] is False

    second = _update(entity, {"progress_state": "STABLE", "kpi": 7}, expected_version=1)
    assert second.status_code == 201
    assert second.json()["state"]["version"] == 2

    history = client.get(f"/api/v1/state-cycle/feat-043/state-history/{entity}")
    assert history.status_code == 200
    assert history.json()["latest_version"] == 2
    assert [x["version"] for x in history.json()["versions"]] == [1, 2]

    link = client.post("/api/v1/state-cycle/feat-044/decision-state-link", json={
        "decision_id": "DEC-001",
        "entity_id": entity,
        "state_version": 2,
        "state_ref": f"{entity}:v2",
        "linked_by": "coach-1",
        "coach_final_authority": True,
    })
    assert link.status_code == 201
    assert link.json()["link"]["state_ref"] == f"{entity}:v2"

    next_state = client.post("/api/v1/state-cycle/feat-045/next-state", json={
        "athlete_id": entity,
        "requested_by": "coach-1",
        "decision_id": "DEC-001",
        "coach_final_authority": True,
    })
    assert next_state.status_code == 200
    result = next_state.json()
    assert result["state"]["version"] == 2
    assert result["linked_decision_state"]["decision_id"] == "DEC-001"
    assert result["execution_authorized"] is False


def test_feat_042_optimistic_version_guard_and_authority():
    entity = "athlete-integration-2"
    assert _update(entity, {"kpi": 5}).status_code == 201

    stale = _update(entity, {"kpi": 6}, expected_version=0)
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_version"] == 1

    blocked = client.post("/api/v1/state-cycle/feat-042/digital-twin-state", json={
        "entity_id": entity,
        "state": {"kpi": 7},
        "source_event": "TEST",
        "case_id": "CASE-002",
        "updated_by": "coach-1",
        "evidence_refs": ["EVID-001"],
        "coach_final_authority": False,
    })
    assert blocked.status_code == 409


def test_feat_044_rejects_non_current_state_reference():
    entity = "athlete-integration-3"
    assert _update(entity, {"kpi": 5}).status_code == 201
    assert _update(entity, {"kpi": 6}, expected_version=1).status_code == 201

    bad_link = client.post("/api/v1/state-cycle/feat-044/decision-state-link", json={
        "decision_id": "DEC-003",
        "entity_id": entity,
        "state_version": 1,
        "state_ref": f"{entity}:v1",
        "linked_by": "coach-1",
        "coach_final_authority": True,
    })
    assert bad_link.status_code == 409
