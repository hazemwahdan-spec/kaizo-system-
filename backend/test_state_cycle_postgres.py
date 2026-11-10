"""Disposable PostgreSQL acceptance for scoped Digital Twin state/history/audit."""
import os
os.environ["KAIZO_IDENTITY_MODE"]="development"
os.environ["KAIZO_PERSISTENCE_MODE"]="postgres"

import sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient
import persistence
from productization import coach_decision_cycles, coach_roster
from state_cycle import router, reset_memory_state

app=FastAPI()
app.include_router(router)
client=TestClient(app,raise_server_exceptions=False)


def _fixture():
    persistence.initialize()
    tenant="T-"+uuid4().hex
    coach="C-"+uuid4().hex
    athlete=coach_roster.create_owned_athlete(
        tenant_id=tenant,coach_actor_id=coach,display_name="Digital Twin PostgreSQL acceptance"
    )
    headers={"X-KAIZO-Actor":coach,"X-KAIZO-Role":"coach","X-KAIZO-Tenant":tenant}
    payload={"entity_id":athlete["athlete_id"],"state":{"kpi":7,"status":"IMPROVING"},
             "source_event":"POSTGRES_RETEST","case_id":"CASE-"+uuid4().hex,
             "evidence_refs":["REF-PG"],"coach_final_authority":True}
    return tenant,coach,athlete["athlete_id"],headers,payload


def test_state_history_and_tenant_audit_persist_under_verified_scope():
    tenant,coach,athlete,headers,payload=_fixture()
    response=client.post("/api/v1/state-cycle/feat-042/digital-twin-state",json=payload,headers=headers)
    assert response.status_code==201,response.text
    body=response.json()
    assert body["state"]["tenant_id"]==tenant
    assert body["state"]["coach_actor_id"]==coach
    assert body["history"]["recorded_by"]==coach
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id,coach_actor_id,version FROM kaizo_digital_twin_state WHERE entity_id=%s",(athlete,))
            assert cur.fetchone()==(tenant,coach,1)
            cur.execute("SELECT tenant_id,coach_actor_id,recorded_by FROM kaizo_digital_twin_history WHERE entity_id=%s",(athlete,))
            assert cur.fetchone()==(tenant,coach,coach)
            cur.execute("SELECT who,action,tenant_id FROM kaizo_audit_logs WHERE action='FEAT-042_STATE_UPDATED' AND new_value->>'entity_id'=%s",(athlete,))
            assert cur.fetchone()==(coach,"FEAT-042_STATE_UPDATED",tenant)
    other={**headers,"X-KAIZO-Actor":coach+"-OTHER"}
    assert client.get(f"/api/v1/state-cycle/feat-042/digital-twin-state/{athlete}",headers=other).status_code==404
    assert client.get(f"/api/v1/state-cycle/feat-043/state-history/{athlete}",headers=other).status_code==404


def test_audit_failure_rolls_back_state_and_history():
    tenant,coach,athlete,headers,payload=_fixture()
    trigger="kaizo_test_reject_state_cycle_audit"
    function="kaizo_test_reject_state_cycle_audit_fn"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
            cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            cur.execute(f"""
                CREATE FUNCTION {function}() RETURNS trigger AS $$
                BEGIN
                    IF NEW.action='FEAT-042_STATE_UPDATED' THEN
                        RAISE EXCEPTION 'intentional state-cycle audit failure';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            cur.execute(f"CREATE TRIGGER {trigger} BEFORE INSERT ON kaizo_audit_logs FOR EACH ROW EXECUTE FUNCTION {function}()")
        conn.commit()
    try:
        response=client.post("/api/v1/state-cycle/feat-042/digital-twin-state",json=payload,headers=headers)
        assert response.status_code==500,response.text
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM kaizo_digital_twin_state WHERE entity_id=%s",(athlete,))
                assert cur.fetchone()[0]==0
                cur.execute("SELECT count(*) FROM kaizo_digital_twin_history WHERE entity_id=%s",(athlete,))
                assert cur.fetchone()[0]==0
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
                cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            conn.commit()


def test_decision_state_link_requires_same_owned_decision_cycle_and_case():
    tenant, coach, athlete, headers, payload = _fixture()
    created = client.post(
        "/api/v1/state-cycle/feat-042/digital-twin-state",
        json=payload, headers=headers,
    )
    assert created.status_code == 201, created.text

    matching = coach_decision_cycles.create_cycle(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete,
        case_id=payload["case_id"], decision_input={"intent":"retest"},
        decision_output={"coach_choice":"review"},
    )
    assert matching is not None
    valid = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={"decision_id":matching["decision_cycle_id"],"entity_id":athlete,
              "state_version":1,"state_ref":f"{athlete}:v1"},
        headers=headers,
    )
    assert valid.status_code == 201, valid.text

    mismatch = coach_decision_cycles.create_cycle(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete,
        case_id="OTHER-" + uuid4().hex, decision_input={"intent":"other"},
        decision_output={"coach_choice":"other"},
    )
    assert mismatch is not None
    mismatch_response = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={"decision_id":mismatch["decision_cycle_id"],"entity_id":athlete,
              "state_version":1,"state_ref":f"{athlete}:v1"},
        headers=headers,
    )
    assert mismatch_response.status_code == 409

    other_coach_athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach + "-OTHER",
        display_name="Different Coach decision-link scope",
    )["athlete_id"]
    other_coach_cycle = coach_decision_cycles.create_cycle(
        tenant_id=tenant, coach_actor_id=coach + "-OTHER", athlete_id=other_coach_athlete,
        case_id=payload["case_id"], decision_input={"intent":"other"},
        decision_output={"coach_choice":"other"},
    )
    assert other_coach_cycle is not None
    other_coach_response = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={"decision_id":other_coach_cycle["decision_cycle_id"],"entity_id":athlete,
              "state_version":1,"state_ref":f"{athlete}:v1"},
        headers=headers,
    )
    assert other_coach_response.status_code == 404

    other_tenant_athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant + "-OTHER", coach_actor_id=coach,
        display_name="Different tenant decision-link scope",
    )["athlete_id"]
    other_tenant_cycle = coach_decision_cycles.create_cycle(
        tenant_id=tenant + "-OTHER", coach_actor_id=coach, athlete_id=other_tenant_athlete,
        case_id=payload["case_id"], decision_input={"intent":"other"},
        decision_output={"coach_choice":"other"},
    )
    assert other_tenant_cycle is not None
    other_tenant_response = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={"decision_id":other_tenant_cycle["decision_cycle_id"],"entity_id":athlete,
              "state_version":1,"state_ref":f"{athlete}:v1"},
        headers=headers,
    )
    assert other_tenant_response.status_code == 404


def test_state_reads_recheck_current_ownership_inside_read_transaction(monkeypatch):
    tenant, coach, athlete, headers, payload = _fixture()
    created = client.post(
        "/api/v1/state-cycle/feat-042/digital-twin-state",
        json=payload, headers=headers,
    )
    assert created.status_code == 201, created.text
    cycle = coach_decision_cycles.create_cycle(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete,
        case_id=payload["case_id"], decision_input={"intent":"retest"},
        decision_output={"coach_choice":"review"},
    )
    assert cycle is not None
    linked = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={
            "decision_id": cycle["decision_cycle_id"],
            "entity_id": athlete,
            "state_version": 1,
            "state_ref": f"{athlete}:v1",
            "coach_final_authority": True,
        },
        headers=headers,
    )
    assert linked.status_code == 201, linked.text
    decision_id = linked.json()["link"]["decision_id"]

    # Simulate ownership changing after the request-level principal check.
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s""",
                (tenant, coach, athlete),
            )

    # Let the route-level check proceed as if it observed the old owner row;
    # the persistence read must independently recheck the authoritative row.
    monkeypatch.setattr(
        coach_roster, "get_owned_athlete",
        lambda **kwargs: {"athlete_id": athlete, "tenant_id": tenant, "coach_actor_id": coach},
    )

    assert client.get(
        f"/api/v1/state-cycle/feat-042/digital-twin-state/{athlete}",
        headers=headers,
    ).status_code == 404
    assert client.get(
        f"/api/v1/state-cycle/feat-043/state-history/{athlete}",
        headers=headers,
    ).status_code == 404
    assert client.get(
        f"/api/v1/state-cycle/feat-044/decision-state-link/{decision_id}",
        params={"athlete_id": athlete},
        headers=headers,
    ).status_code == 404
