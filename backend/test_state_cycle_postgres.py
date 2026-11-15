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
    athlete_id=athlete["athlete_id"]
    evidence_id="EVIDENCE-"+uuid4().hex
    now="2026-11-14T00:00:00+00:00"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_evidence_records
                   (evidence_id,subject_type,subject_id,evidence_level,status,
                    source_ref,claim,observed_value,verified_by,verified_at,notes)
                   VALUES (%s,'athlete',%s,'E3','VERIFIED',%s,%s,
                           '{"kpi":7}'::jsonb,%s,%s,%s)""",
                (evidence_id,athlete_id,"fixture:"+evidence_id,
                 "Verified Digital Twin athlete evidence",coach,now,
                 "Disposable PostgreSQL acceptance fixture"),
            )
        conn.commit()
    payload={"entity_id":athlete_id,"state":{"kpi":7,"status":"IMPROVING"},
             "source_event":"POSTGRES_RETEST","case_id":"CASE-"+uuid4().hex,
             "evidence_refs":[evidence_id],"coach_final_authority":True}
    return tenant,coach,athlete_id,headers,payload


def _seed_decision(coach, athlete):
    decision_id = "DECISION-" + uuid4().hex
    now = "2026-11-15T00:00:00+00:00"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_decision_records
                   (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,
                    assessment_id,candidate_type,coach_action,coach_id,
                    decision_summary,outcome_intent,status,recorded_at)
                   VALUES (%s,%s,%s,%s,%s,%s,'DIRECT_INTERVENTION','RETEST',%s,
                           'Scoped test decision','Verify improvement','RECORDED',%s)""",
                (decision_id, "CAND-" + uuid4().hex, "DIAG-" + uuid4().hex,
                 "PROBLEM-" + uuid4().hex, athlete, "ASSESSMENT-" + uuid4().hex,
                 coach, now),
            )
        conn.commit()
    return decision_id


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


def test_digital_twin_rejects_missing_unverified_foreign_wrong_coach_and_e0_evidence():
    tenant,coach,athlete,headers,payload=_fixture()
    foreign=coach_roster.create_owned_athlete(
        tenant_id=tenant,coach_actor_id=coach+"-OTHER",
        display_name="Foreign evidence owner",
    )
    unverified="EVIDENCE-UNVERIFIED-"+uuid4().hex
    foreign_evidence="EVIDENCE-FOREIGN-"+uuid4().hex
    wrong_coach="EVIDENCE-WRONG-COACH-"+uuid4().hex
    e0="EVIDENCE-E0-"+uuid4().hex
    now="2026-11-14T00:00:00+00:00"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_evidence_records
                   (evidence_id,subject_type,subject_id,evidence_level,status,
                    source_ref,claim,verified_by,verified_at,notes)
                   VALUES
                   (%s,'athlete',%s,'E3','UNVERIFIED',%s,'Unverified fixture',%s,%s,'test'),
                   (%s,'athlete',%s,'E3','VERIFIED',%s,'Foreign athlete fixture',%s,%s,'test'),
                   (%s,'athlete',%s,'E3','VERIFIED',%s,'Wrong Coach fixture',%s,%s,'test'),
                   (%s,'athlete',%s,'E0','VERIFIED',%s,'E0 fixture',%s,%s,'test')""",
                (unverified,athlete,"fixture:"+unverified,coach,now,
                 foreign_evidence,foreign["athlete_id"],"fixture:"+foreign_evidence,coach,now,
                 wrong_coach,athlete,"fixture:"+wrong_coach,coach+"-OTHER",now,
                 e0,athlete,"fixture:"+e0,coach,now),
            )
        conn.commit()
    invalid_refs=[
        "MISSING-EVIDENCE-"+uuid4().hex,
        unverified,
        foreign_evidence,
        wrong_coach,
        e0,
        payload["evidence_refs"][0] + "-duplicate",
    ]
    for evidence_ref in invalid_refs:
        response=client.post(
            "/api/v1/state-cycle/feat-042/digital-twin-state",
            json={**payload,"evidence_refs":[evidence_ref]},headers=headers,
        )
        assert response.status_code==409,response.text
    duplicate=client.post(
        "/api/v1/state-cycle/feat-042/digital-twin-state",
        json={**payload,"evidence_refs":[payload["evidence_refs"][0],payload["evidence_refs"][0]]},
        headers=headers,
    )
    assert duplicate.status_code==409,duplicate.text
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM kaizo_digital_twin_state WHERE entity_id=%s",(athlete,))
            assert cur.fetchone()[0]==0
            cur.execute("SELECT COUNT(*) FROM kaizo_digital_twin_history WHERE entity_id=%s",(athlete,))
            assert cur.fetchone()[0]==0
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s
                     AND action='FEAT-042_STATE_UPDATED'
                     AND new_value->>'entity_id'=%s""",
                (tenant,coach,athlete),
            )
            assert cur.fetchone()[0]==0


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


def test_decision_state_link_rejects_cross_coach_and_cross_tenant_decisions():
    tenant, coach, athlete, headers, payload = _fixture()
    created = client.post(
        "/api/v1/state-cycle/feat-042/digital-twin-state",
        json=payload, headers=headers,
    )
    assert created.status_code == 201, created.text

    other_coach = coach + "-OTHER"
    same_athlete_wrong_coach = _seed_decision(other_coach, athlete)
    other_athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=other_coach,
        display_name="Foreign Coach decision athlete",
    )
    cross_coach_decision = _seed_decision(other_coach, other_athlete["athlete_id"])
    other_tenant_athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant + "-OTHER", coach_actor_id=coach,
        display_name="Foreign Tenant decision athlete",
    )
    cross_tenant_decision = _seed_decision(coach, other_tenant_athlete["athlete_id"])

    for decision_id in (
        same_athlete_wrong_coach, cross_coach_decision, cross_tenant_decision,
        "MISSING-DECISION-" + uuid4().hex,
    ):
        response = client.post(
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
        assert response.status_code == 404, response.text

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM kaizo_decision_state_links WHERE entity_id=%s",
                (athlete,),
            )
            assert cur.fetchone()[0] == 0
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s
                     AND action='FEAT-044_DECISION_STATE_LINKED'
                     AND new_value->>'entity_id'=%s""",
                (tenant, coach, athlete),
            )
            assert cur.fetchone()[0] == 0

    valid_decision = _seed_decision(coach, athlete)
    accepted = client.post(
        "/api/v1/state-cycle/feat-044/decision-state-link",
        json={
            "decision_id": valid_decision,
            "entity_id": athlete,
            "state_version": 1,
            "state_ref": f"{athlete}:v1",
            "coach_final_authority": True,
        },
        headers=headers,
    )
    assert accepted.status_code == 201, accepted.text
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT decision_id,tenant_id,coach_actor_id
                   FROM kaizo_decision_state_links WHERE entity_id=%s""",
                (athlete,),
            )
            assert cur.fetchone() == (valid_decision, tenant, coach)


def test_decision_state_link_rolls_back_when_tenant_audit_fails():
    tenant, coach, athlete, headers, payload = _fixture()
    created = client.post(
        "/api/v1/state-cycle/feat-042/digital-twin-state",
        json=payload, headers=headers,
    )
    assert created.status_code == 201, created.text
    decision_id = _seed_decision(coach, athlete)
    trigger = "kaizo_test_reject_feat044_audit_" + uuid4().hex[:12]
    function = trigger + "_fn"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
            cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            cur.execute(f"""
                CREATE FUNCTION {function}() RETURNS trigger AS $fn$
                BEGIN
                    IF NEW.action='FEAT-044_DECISION_STATE_LINKED' THEN
                        RAISE EXCEPTION 'intentional FEAT-044 audit failure';
                    END IF;
                    RETURN NEW;
                END;
                $fn$ LANGUAGE plpgsql
            """)
            cur.execute(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON kaizo_audit_logs "
                f"FOR EACH ROW EXECUTE FUNCTION {function}()"
            )
        conn.commit()
    try:
        response = client.post(
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
        assert response.status_code == 500, response.text
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM kaizo_decision_state_links WHERE entity_id=%s",
                    (athlete,),
                )
                assert cur.fetchone()[0] == 0
                cur.execute(
                    """SELECT COUNT(*) FROM kaizo_audit_logs
                       WHERE tenant_id=%s AND who=%s
                         AND action='FEAT-044_DECISION_STATE_LINKED'
                         AND new_value->>'entity_id'=%s""",
                    (tenant, coach, athlete),
                )
                assert cur.fetchone()[0] == 0
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
                cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            conn.commit()


def test_state_reads_recheck_current_ownership_inside_read_transaction(monkeypatch):
    tenant, coach, athlete, headers, payload = _fixture()
    created = client.post(
        "/api/v1/state-cycle/feat-042/digital-twin-state",
        json=payload, headers=headers,
    )
    assert created.status_code == 201, created.text
    decision_id = _seed_decision(coach, athlete)
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
