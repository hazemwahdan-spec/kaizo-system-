import os
os.environ["KAIZO_PERSISTENCE_MODE"]="memory"
os.environ["KAIZO_IDENTITY_MODE"]="development"

from fastapi.testclient import TestClient
from main import app
from productization import coach_roster
from state_cycle import reset_memory_state

client=TestClient(app)
COACH={"X-KAIZO-Actor":"coach-1","X-KAIZO-Role":"coach","X-KAIZO-Tenant":"tenant-1"}
OTHER={"X-KAIZO-Actor":"coach-2","X-KAIZO-Role":"coach","X-KAIZO-Tenant":"tenant-1"}
TENANT={"X-KAIZO-Actor":"coach-1","X-KAIZO-Role":"coach","X-KAIZO-Tenant":"tenant-2"}


def setup_function():
    reset_memory_state()
    coach_roster.reset_memory_state()
    global ATHLETE
    ATHLETE=coach_roster.create_owned_athlete(
        tenant_id="tenant-1",coach_actor_id="coach-1",display_name="State cycle test athlete"
    )["athlete_id"]


def update_payload():
    return {"entity_id":ATHLETE,"state":{"progress":"IMPROVING","kpi":6},
            "source_event":"RETEST_COMPLETE","case_id":"CASE-1",
            "evidence_refs":["REF-1"],"coach_final_authority":True,
            "updated_by":"spoofed-client-actor"}


def test_feat_042_to_045_requires_authenticated_owned_coach_and_preserves_lineage():
    first=client.post("/api/v1/state-cycle/feat-042/digital-twin-state",
                      json=update_payload(),headers=COACH)
    assert first.status_code==201,first.text
    assert first.json()["state"]["version"]==1
    assert first.json()["history"]["recorded_by"]=="coach-1"
    assert first.json()["state"]["execution_authorized"] is False

    second=client.post("/api/v1/state-cycle/feat-042/digital-twin-state",
        json={**update_payload(),"state":{"progress":"STABLE","kpi":7},"expected_version":1},
        headers=COACH)
    assert second.status_code==201
    assert second.json()["state"]["version"]==2

    history=client.get(f"/api/v1/state-cycle/feat-043/state-history/{ATHLETE}",headers=COACH)
    assert history.status_code==200
    assert [x["version"] for x in history.json()["versions"]]==[1,2]
    assert all(x["recorded_by"]=="coach-1" for x in history.json()["versions"])

    link=client.post("/api/v1/state-cycle/feat-044/decision-state-link",
        json={"decision_id":"DEC-1","entity_id":ATHLETE,"state_version":2,
              "state_ref":f"{ATHLETE}:v2","linked_by":"spoofed-actor"},
        headers=COACH)
    assert link.status_code==201,link.text
    assert link.json()["link"]["linked_by"]=="coach-1"

    nxt=client.post("/api/v1/state-cycle/feat-045/next-state",
        json={"athlete_id":ATHLETE,"decision_id":"DEC-1","requested_by":"spoofed-actor"},
        headers=COACH)
    assert nxt.status_code==200,nxt.text
    assert nxt.json()["linked_decision_state"]["decision_id"]=="DEC-1"
    assert nxt.json()["coach_actor_id"]=="coach-1"
    assert nxt.json()["execution_authorized"] is False


def test_anonymous_non_coach_cross_coach_and_cross_tenant_denied():
    path="/api/v1/state-cycle/feat-042/digital-twin-state"
    assert client.post(path,json=update_payload()).status_code==401
    assert client.post(path,json=update_payload(),headers={**COACH,"X-KAIZO-Role":"athlete"}).status_code==403
    assert client.post(path,json=update_payload(),headers=OTHER).status_code==404
    assert client.post(path,json=update_payload(),headers=TENANT).status_code==404
    assert client.get(f"/api/v1/state-cycle/feat-042/digital-twin-state/{ATHLETE}",headers=OTHER).status_code==404
    assert client.get(f"/api/v1/state-cycle/feat-043/state-history/{ATHLETE}",headers=TENANT).status_code==404


def test_all_state_cycle_reads_and_writes_require_ownership():
    assert client.get(f"/api/v1/state-cycle/feat-042/digital-twin-state/{ATHLETE}").status_code==401
    assert client.get(f"/api/v1/state-cycle/feat-043/state-history/{ATHLETE}").status_code==401
    assert client.post("/api/v1/state-cycle/feat-044/decision-state-link",
        json={"decision_id":"D","entity_id":ATHLETE,"state_version":1,"state_ref":f"{ATHLETE}:v1"},
    ).status_code==401
    assert client.post("/api/v1/state-cycle/feat-045/next-state",
        json={"athlete_id":ATHLETE}).status_code==401


def test_version_conflict_and_coach_authority_fail_closed():
    assert client.post("/api/v1/state-cycle/feat-042/digital-twin-state",
        json={**update_payload(),"expected_version":9},headers=COACH).status_code==409
    assert client.post("/api/v1/state-cycle/feat-042/digital-twin-state",
        json={**update_payload(),"coach_final_authority":False},headers=COACH).status_code==409



def decision_loop_payload(athlete_id=ATHLETE):
    return {
        "case_id": "CASE-OWNERSHIP-1", "athlete_id": athlete_id,
        "decision": {"selected": "candidate-A"},
        "intervention": {"drill": "seoi"},
        "response_kpi": {"entry_quality": 7},
        "retest": {"result": "PASS"},
        "coach_final_authority": True,
    }


def adaptation_payload(athlete_id=ATHLETE):
    return {
        "case_id": "CASE-OWNERSHIP-1", "athlete_id": athlete_id,
        "operation": "individual_adaptation",
        "common_core": {"plan": "CORE-A"},
        "dynamic_inputs": {"retest": "PASS"},
        "individual_change": {"task": "shorter decision window"},
        "coach_final_authority": True,
    }


def test_legacy_decision_loop_and_adaptation_routes_require_owned_coach_scope():
    for path, payload in (
        ("/api/v1/decision/loop", decision_loop_payload()),
        ("/api/v1/decision/adapt", adaptation_payload()),
    ):
        assert client.post(path, json=payload).status_code == 401
        assert client.post(path, json=payload, headers={**COACH, "X-KAIZO-Role": "athlete"}).status_code == 403
        assert client.post(path, json=payload, headers=OTHER).status_code == 404
        assert client.post(path, json=payload, headers=TENANT).status_code == 404
        assert client.post(path, json={k: v for k, v in payload.items() if k != "athlete_id"},
                           headers=COACH).status_code == 422


def test_case_id_and_caller_authority_boolean_do_not_grant_athlete_access():
    other_athlete = coach_roster.create_owned_athlete(
        tenant_id="tenant-1", coach_actor_id="coach-2", display_name="Other Coach athlete"
    )["athlete_id"]
    payload = decision_loop_payload(athlete_id=other_athlete)
    # A matching case_id and a true caller boolean cannot cross the ownership boundary.
    assert client.post("/api/v1/decision/loop", json=payload, headers=COACH).status_code == 404

    own_payload = {**decision_loop_payload(), "coach_final_authority": False}
    held = client.post("/api/v1/decision/loop", json=own_payload, headers=COACH)
    assert held.status_code == 200
    assert held.json()["status"] == "HOLD"
    assert held.json()["recorded_by"] == "coach-1"


def test_owned_coach_can_execute_scoped_decision_and_adaptation():
    loop = client.post("/api/v1/decision/loop", json=decision_loop_payload(), headers=COACH)
    assert loop.status_code == 200, loop.text
    assert loop.json()["status"] == "LOOP_COMPLETED"
    assert loop.json()["athlete_id"] == ATHLETE
    assert loop.json()["recorded_by"] == "coach-1"

    adapted = client.post("/api/v1/decision/adapt", json=adaptation_payload(), headers=COACH)
    assert adapted.status_code == 200, adapted.text
    assert adapted.json()["status"] == "ADAPTED"
    assert adapted.json()["athlete_id"] == ATHLETE
    assert adapted.json()["recorded_by"] == "coach-1"
