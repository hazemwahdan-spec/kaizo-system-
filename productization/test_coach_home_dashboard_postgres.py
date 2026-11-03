"""FEAT-006 real PostgreSQL Coach dashboard aggregation and tenant isolation."""
import sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"backend"))
import persistence
from productization import coach_roster, coach_groups

def test_postgres_dashboard_aggregates_only_owned_athletes_groups_and_decisions():
    assert persistence.is_postgres_enabled();persistence.initialize()
    tenant="TENANT-"+uuid4().hex;coach="COACH-"+uuid4().hex
    athlete=coach_roster.create_owned_athlete(tenant_id=tenant,coach_actor_id=coach,display_name="FEAT006 owned")
    foreign=coach_roster.create_owned_athlete(tenant_id=tenant,coach_actor_id="OTHER-COACH",display_name="FEAT006 foreign")
    group=coach_groups.create_group(tenant_id=tenant,coach_actor_id=coach,name="Dashboard group")
    assert coach_groups.assign_athlete(tenant_id=tenant,coach_actor_id=coach,group_id=group["group_id"],athlete_id=athlete["athlete_id"])
    decision="DASH-"+uuid4().hex
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO kaizo_decision_records
                (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                 candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (decision,"C-"+uuid4().hex,"DIAG-1","PROB-1",athlete["athlete_id"],"ASSESS-1",
                 "TECHNICAL_ADAPTATION","CONFIRM",coach,"FEAT006 decision","Improve entry","RECORDED","2026-11-01T10:00:00"))
            cur.execute("""INSERT INTO kaizo_decision_records
                (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                 candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                ("FOREIGN-"+uuid4().hex,"C-"+uuid4().hex,"DIAG-1","PROB-1",foreign["athlete_id"],"ASSESS-1",
                 "TECHNICAL_ADAPTATION","CONFIRM","OTHER-COACH","Foreign decision","Ignore","RECORDED","2026-11-02T10:00:00"))
    dashboard=coach_roster.get_coach_home_dashboard(tenant_id=tenant,coach_actor_id=coach)
    assert dashboard["athlete_total"]==1
    assert dashboard["training_group_total"]==1 and dashboard["group_membership_total"]==1
    assert dashboard["decision_cycle_total"]==1
    assert dashboard["recent_decisions"][0]["decision_id"]==decision
    assert dashboard["execution_authorized"] is False
