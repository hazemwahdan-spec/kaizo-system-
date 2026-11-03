"""FEAT-007 PostgreSQL scope, evidence, and read-only acceptance."""
import sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"backend"))
import persistence
from productization import coach_roster, coach_priority_queue


def test_postgres_queue_uses_only_owned_workflow_evidence_and_does_not_write():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant="TENANT-"+uuid4().hex;coach="COACH-"+uuid4().hex
    owned=coach_roster.create_owned_athlete(tenant_id=tenant,coach_actor_id=coach,display_name="FEAT007 owned")
    foreign=coach_roster.create_owned_athlete(tenant_id=tenant,coach_actor_id="OTHER-"+uuid4().hex,display_name="FEAT007 foreign")
    other_tenant=coach_roster.create_owned_athlete(tenant_id="TENANT-"+uuid4().hex,coach_actor_id=coach,display_name="FEAT007 other tenant")
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_training_workflow_records (
                    record_id TEXT PRIMARY KEY, feature_id TEXT NOT NULL,
                    athlete_id TEXT NOT NULL, decision_id TEXT, session_id TEXT,
                    payload JSONB NOT NULL, created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL, coach_final_authority BOOLEAN NOT NULL,
                    execution_authorized BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)
            rows=[
                ("OWN-RESP","FEAT-036",owned["athlete_id"],"D1","S1",
                 '{"response":{"kpi":"grip"}}',"coach", "2026-11-01T10:00:00"),
                ("OWN-TRIGGER","FEAT-040",owned["athlete_id"],None,"S2",
                 '{"trigger_type":"RETEST","trigger_reason":"Retest changed baseline","required_evidence":["EV-1"]}',
                 "coach","2026-11-02T10:00:00"),
                ("FOREIGN-TRIGGER","FEAT-040",foreign["athlete_id"],None,"S3",
                 '{"trigger_type":"RETEST","trigger_reason":"foreign","required_evidence":["EV-X"]}',
                 "other","2026-11-03T10:00:00"),
                ("TENANT-TRIGGER","FEAT-040",other_tenant["athlete_id"],None,"S4",
                 '{"trigger_type":"RETEST","trigger_reason":"other tenant","required_evidence":["EV-Y"]}',
                 "other","2026-11-04T10:00:00"),
            ]
            for row in rows:
                cur.execute("""INSERT INTO kaizo_training_workflow_records
                    (record_id,feature_id,athlete_id,decision_id,session_id,payload,
                     created_by,created_at,coach_final_authority,execution_authorized)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,TRUE,FALSE)
                    ON CONFLICT (record_id) DO NOTHING""",row)
            cur.execute("SELECT COUNT(*) FROM kaizo_training_workflow_records WHERE record_id IN ('OWN-RESP','OWN-TRIGGER')")
            before=cur.fetchone()[0]
    result=coach_priority_queue.get_coach_priority_queue(tenant_id=tenant,coach_actor_id=coach)
    assert result["available"] is True
    assert result["item_count"]==2
    assert {x["item_id"] for x in result["items"]}=={"OWN-RESP","OWN-TRIGGER"}
    assert all(x["athlete_id"]==owned["athlete_id"] for x in result["items"])
    assert all(x["priority_rank"] is None and x["due_at"] is None for x in result["items"])
    assert result["execution_authorized"] is False
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM kaizo_training_workflow_records WHERE record_id IN ('OWN-RESP','OWN-TRIGGER')")
            after=cur.fetchone()[0]
    assert before==after
