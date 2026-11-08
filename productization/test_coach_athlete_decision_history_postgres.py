"""FEAT-005 PostgreSQL integration: ownership-scoped persisted decision history."""
import sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"backend"))
import persistence, training_workflow
from productization import coach_roster

def test_postgres_decision_history_uses_existing_records_and_respects_owner_scope():
    assert persistence.is_postgres_enabled();persistence.initialize();training_workflow._ensure_schema()
    tenant="TENANT-"+uuid4().hex;coach="COACH-"+uuid4().hex
    athlete=coach_roster.create_owned_athlete(tenant_id=tenant,coach_actor_id=coach,display_name="FEAT-005 PG")
    aid=athlete["athlete_id"];decision="DEC-"+uuid4().hex;record="WF-"+uuid4().hex
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO kaizo_decision_records
                (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                 candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (decision,"CAND-"+uuid4().hex,"DIAG-1","PROB-1",aid,"ASSESS-1",
                 "TECHNICAL_ADAPTATION","CONFIRM",coach,"Decision history PG",
                 "Improve entry timing","RECORDED","2026-10-20T10:00:00"))
            cur.execute("""INSERT INTO kaizo_training_workflow_records
                (record_id,feature_id,athlete_id,decision_id,session_id,payload,created_by,
                 created_at,coach_final_authority,execution_authorized)
                VALUES (%s,%s,%s,%s,%s,'{}'::jsonb,%s,%s,TRUE,FALSE)""",
                (record,"FEAT-033",aid,decision,"SESSION-1",coach,"2026-10-21T10:00:00"))
    cycles=coach_roster.list_owned_athlete_decision_cycles(tenant_id=tenant,coach_actor_id=coach,athlete_id=aid)
    assert cycles is not None and len(cycles)==1
    assert cycles[0]["decision_id"]==decision
    assert cycles[0]["training_records"][0]["record_id"]==record
    assert coach_roster.list_owned_athlete_decision_cycles(tenant_id=tenant,coach_actor_id="OTHER",athlete_id=aid) is None
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM kaizo_decision_records WHERE decision_id=%s",(decision,))
            assert cur.fetchone()[0]==1
            cur.execute("SELECT COUNT(*) FROM kaizo_training_workflow_records WHERE record_id=%s",(record,))
            assert cur.fetchone()[0]==1
