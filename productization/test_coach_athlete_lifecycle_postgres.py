"""Real PostgreSQL persistence and tenant audit test for FEAT-004."""
import sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"backend"))
import persistence
from productization import coach_roster

def test_postgres_lifecycle_transition_history_and_audit_are_durable():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant="TENANT-"+uuid4().hex;coach="COACH-"+uuid4().hex
    athlete=coach_roster.create_owned_athlete(tenant_id=tenant,coach_actor_id=coach,display_name="Lifecycle PG")
    aid=athlete["athlete_id"]
    result=coach_roster.update_owned_athlete_status(tenant_id=tenant,coach_actor_id=coach,
        athlete_id=aid,new_status="SUSPENDED",reason="PostgreSQL lifecycle acceptance")
    assert result["changed"] and result["previous_status"]=="ACTIVE" and result["status"]=="SUSPENDED"
    history=coach_roster.list_owned_athlete_status_history(tenant_id=tenant,coach_actor_id=coach,athlete_id=aid)
    assert len(history)==1 and history[0]["new_status"]=="SUSPENDED"
    assert coach_roster.update_owned_athlete_status(tenant_id=tenant,coach_actor_id="OTHER",
        athlete_id=aid,new_status="ACTIVE",reason="must not access") is None
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM kaizo_athletes WHERE athlete_id=%s",(aid,))
            assert cur.fetchone()[0]=="SUSPENDED"
            cur.execute("""SELECT action,tenant_id,old_value,new_value,why FROM kaizo_audit_logs
                WHERE who=%s AND action='COACH_ATHLETE_STATUS_CHANGED' ORDER BY id DESC LIMIT 1""",(coach,))
            event=cur.fetchone()
    assert event[0]=="COACH_ATHLETE_STATUS_CHANGED" and event[1]==tenant
    assert event[2]["status"]=="ACTIVE" and event[3]["status"]=="SUSPENDED"
    assert event[4]=="PostgreSQL lifecycle acceptance"
