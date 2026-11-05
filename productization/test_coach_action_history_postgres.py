"""FEAT-010 PostgreSQL integration: verified actor/tenant audit and FEAT-044 lineage."""
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import persistence
import state_cycle
from productization import coach_roster, coach_action_history


def test_action_history_is_tenant_actor_and_owned_athlete_scoped_and_read_only():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    state_cycle._ensure_schema()

    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    owned = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="FEAT-010 owner"
    )
    foreign_coach = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id="COACH-" + uuid4().hex,
        display_name="FEAT-010 other coach"
    )
    foreign_tenant = coach_roster.create_owned_athlete(
        tenant_id="TENANT-" + uuid4().hex, coach_actor_id=coach,
        display_name="FEAT-010 other tenant"
    )
    aid = owned["athlete_id"]
    decision = "DEC-" + uuid4().hex
    foreign_decision = "DEC-" + uuid4().hex
    now = "2026-11-03T12:00:00+00:00"

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            for decision_id, athlete_id in (
                (decision, aid),
                (foreign_decision, foreign_coach["athlete_id"]),
            ):
                cur.execute("""
                    INSERT INTO kaizo_decision_records
                    (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                     candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                    VALUES (%s,%s,%s,%s,%s,%s,'TECHNICAL_ADAPTATION','CONFIRM',%s,
                            'Decision history fixture','Outcome intent','RECORDED',%s)
                """, (decision_id, "C-" + decision_id, "D-" + decision_id, "P-" + decision_id,
                      athlete_id, "A-" + decision_id, coach, now))

            audit_rows = [
                (coach, "COACH_ATHLETE_STATUS_CHANGED", {"athlete_id": aid}, tenant),
                ("COACH-OTHER", "COACH_ATHLETE_STATUS_CHANGED", {"athlete_id": aid}, tenant),
                (coach, "FOREIGN_TENANT_SENTINEL", {"athlete_id": aid}, "TENANT-OTHER"),
                (coach, "LEGACY_UNSCOPED_EVENT", {"athlete_id": aid}, None),
                (coach, "FOREIGN_ATHLETE_EVENT", {"athlete_id": foreign_coach["athlete_id"]}, tenant),
                (coach, "COACH_DECISION_RECORDED", {"decision_id": decision}, tenant),
            ]
            for who, action, new_value, row_tenant in audit_rows:
                cur.execute("""
                    INSERT INTO kaizo_audit_logs(timestamp,who,action,old_value,new_value,why,tenant_id)
                    VALUES (%s,%s,%s,'null',%s::jsonb,'FEAT-010 test event',%s)
                """, (now, who, action, json.dumps(new_value), row_tenant))

            cur.execute("""
                INSERT INTO kaizo_decision_state_links
                (link_id,decision_id,entity_id,state_version,state_ref,linked_by,linked_at,
                 coach_final_authority,execution_authorized)
                VALUES (%s,%s,%s,2,%s,'UNVERIFIED-CLIENT-CLAIM',%s,TRUE,FALSE)
            """, ("LINK-" + uuid4().hex, decision, aid, aid + ":v2", now))
            cur.execute("""
                INSERT INTO kaizo_decision_state_links
                (link_id,decision_id,entity_id,state_version,state_ref,linked_by,linked_at,
                 coach_final_authority,execution_authorized)
                VALUES (%s,%s,%s,2,%s,'UNVERIFIED-CLIENT-CLAIM',%s,TRUE,FALSE)
            """, ("LINK-" + uuid4().hex, foreign_decision, aid, aid + ":v2", now))

            cur.execute("SELECT COUNT(*) FROM kaizo_audit_logs")
            audit_before = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM kaizo_decision_state_links")
            links_before = cur.fetchone()[0]

    result = coach_action_history.get_coach_action_history(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=aid
    )
    assert result["available"] is True
    assert result["status"] == "ACTION_HISTORY_AVAILABLE"
    audit_items = [x for x in result["items"] if x["source"] == "TENANT_SCOPED_AUDIT"]
    state_items = [x for x in result["items"] if x["source"] == "FEAT-044_DECISION_STATE_LINK"]
    assert {x["action"] for x in audit_items} == {"COACH_ATHLETE_CREATED", "COACH_ATHLETE_STATUS_CHANGED", "COACH_DECISION_RECORDED"}
    assert all(x["actor_id"] == coach and x["actor_attribution_verified"] is True for x in audit_items)
    assert "FOREIGN_TENANT_SENTINEL" not in {x["action"] for x in audit_items}
    assert len(state_items) == 1
    assert state_items[0]["decision_id"] == decision
    assert state_items[0]["actor_id"] is None
    assert state_items[0]["actor_attribution_verified"] is False
    assert "UNVERIFIED-CLIENT-CLAIM" not in str(result)

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM kaizo_audit_logs")
            audit_after = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM kaizo_decision_state_links")
            links_after = cur.fetchone()[0]
    assert audit_before == audit_after
    assert links_before == links_after
