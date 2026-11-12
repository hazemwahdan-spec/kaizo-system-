"""Disposable PostgreSQL acceptance for scoped Digital Twin state/history/audit."""
import os
import json
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
from productization import coach_roster
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
    athlete_id=athlete["athlete_id"]
    headers={"X-KAIZO-Actor":coach,"X-KAIZO-Role":"coach","X-KAIZO-Tenant":tenant}
    payload={"entity_id":athlete_id,"state":{"kpi":7,"status":"IMPROVING"},
             "source_event":"POSTGRES_RETEST","case_id":"CASE-"+uuid4().hex,
             "evidence_refs":["REF-PG"],"coach_final_authority":True}
    decision_id="DECISION-"+uuid4().hex
    candidate_id="CANDIDATE-"+uuid4().hex
    diagnosis_id="DIAGNOSIS-"+uuid4().hex
    problem_id="PROBLEM-"+uuid4().hex
    assessment_id="ASSESSMENT-"+uuid4().hex
    now="2026-11-12T00:00:00+00:00"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_decision_records
                   (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                    candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                   VALUES (%s,%s,%s,%s,%s,%s,'TECHNICAL_ADAPTATION','CONFIRM',%s,
                           'Recorded Coach decision','Retest and compare','RECORDED',%s)""",
                (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,coach,now),
            )
            cur.execute(
                """INSERT INTO kaizo_audit_logs
                   (timestamp,who,action,old_value,new_value,why,tenant_id)
                   VALUES (%s,%s,'COACH_DECISION_RECORD_RECORDED',NULL,%s::jsonb,%s,%s)""",
                (now,coach,json.dumps({"decision_id":decision_id,"athlete_id":athlete_id,
                                       "coach_id":coach,"status":"RECORDED"}),
                 "Trusted recorded decision fixture for state-cycle tests",tenant),
            )
        conn.commit()
    return tenant,coach,athlete_id,headers,payload,decision_id


def test_state_history_and_tenant_audit_persist_under_verified_scope():
    tenant,coach,athlete,headers,payload,_decision_id=_fixture()
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
    tenant,coach,athlete,headers,payload,_decision_id=_fixture()
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


def test_state_reads_recheck_current_ownership_inside_read_transaction(monkeypatch):
    tenant, coach, athlete, headers, payload, decision_id = _fixture()
    created = client.post(
        "/api/v1/state-cycle/feat-042/digital-twin-state",
        json=payload, headers=headers,
    )
    assert created.status_code == 201, created.text
    linked = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={
            "decision_id": decision_id,
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
