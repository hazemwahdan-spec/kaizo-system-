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
