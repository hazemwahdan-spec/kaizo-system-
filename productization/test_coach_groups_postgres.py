"""PostgreSQL durability and tenant-audit integration for Coach groups."""
import sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"backend"))
import persistence
from productization import coach_roster,coach_groups

def test_postgres_persists_group_membership_and_tenant_audit():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant="TENANT-"+uuid4().hex;coach="COACH-"+uuid4().hex
    athlete=coach_roster.create_owned_athlete(tenant_id=tenant,coach_actor_id=coach,display_name="Group member")
    group=coach_groups.create_group(tenant_id=tenant,coach_actor_id=coach,name="U15 acceptance")
    assert coach_groups.assign_athlete(tenant_id=tenant,coach_actor_id=coach,group_id=group["group_id"],athlete_id=athlete["athlete_id"])
    rows=coach_groups.list_groups(tenant_id=tenant,coach_actor_id=coach)
    assert rows[0]["athletes"][0]["athlete_id"]==athlete["athlete_id"]
    assert coach_groups.list_groups(tenant_id="OTHER",coach_actor_id=coach)==[]
    assert coach_groups.unassign_athlete(tenant_id=tenant,coach_actor_id=coach,group_id=group["group_id"],athlete_id=athlete["athlete_id"])
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT action,tenant_id FROM kaizo_audit_logs
                WHERE who=%s AND action IN ('COACH_TRAINING_GROUP_CREATED',
                'COACH_TRAINING_GROUP_ATHLETE_ASSIGNED',
                'COACH_TRAINING_GROUP_ATHLETE_UNASSIGNED') ORDER BY id""",(coach,))
            events=cur.fetchall()
    assert [x[0] for x in events]==["COACH_TRAINING_GROUP_CREATED","COACH_TRAINING_GROUP_ATHLETE_ASSIGNED","COACH_TRAINING_GROUP_ATHLETE_UNASSIGNED"]
    assert all(x[1]==tenant for x in events)
