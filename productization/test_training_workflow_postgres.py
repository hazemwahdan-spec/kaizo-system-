"""PostgreSQL acceptance for scoped FEAT-033..040 lineage and atomic tenant audit."""
import json
import os
import sys
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["KAIZO_IDENTITY_MODE"] = "development"
os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"

from fastapi import FastAPI
from fastapi.testclient import TestClient

import persistence
import training_workflow
from productization import coach_roster
from training_workflow import router

app = FastAPI()
app.include_router(router)
client = TestClient(app, raise_server_exceptions=False)


def _seed_lineage(tenant: str, coach: str, athlete_id: str) -> dict[str, str]:
    ids = {
        "assessment_id": "ASSESS-" + uuid4().hex,
        "evidence_id": "EVIDENCE-" + uuid4().hex,
        "problem_id": "PROBLEM-" + uuid4().hex,
        "diagnosis_id": "DIAGNOSIS-" + uuid4().hex,
        "candidate_id": "CANDIDATE-" + uuid4().hex,
        "review_id": "REVIEW-" + uuid4().hex,
        "decision_id": "DECISION-" + uuid4().hex,
        "plan_id": "PLAN-" + uuid4().hex,
        "session_id": "SESSION-" + uuid4().hex,
        "drill_id": "DRILL-" + uuid4().hex,
        "link_id": "LINK-" + uuid4().hex,
    }
    now = datetime.now(timezone.utc).isoformat()
    measurements = {"entry_success": 4}
    evidence_ids = json.dumps([ids["evidence_id"]])
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_assessments
                   (assessment_id,athlete_id,template_id,measurements,recorded_by,assessed_at,created_at)
                   VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                (ids["assessment_id"], athlete_id, "JUDO-BASELINE",
                 json.dumps(measurements), coach, now, now),
            )
            cur.execute(
                """INSERT INTO kaizo_evidence_records
                   (evidence_id,subject_type,subject_id,evidence_level,status,source_ref,
                    claim,observed_value,verified_by,verified_at,notes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                (ids["evidence_id"], "assessment", ids["assessment_id"], "E3",
                 "VERIFIED", "test://baseline", "Verified baseline assessment",
                 json.dumps(measurements), coach, now, "isolated acceptance fixture"),
            )
            cur.execute(
                """INSERT INTO kaizo_problem_statements
                   (problem_id,athlete_id,assessment_id,statement,problem_type,impact,
                    context,structured_fields,status,created_by,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)""",
                (ids["problem_id"], athlete_id, ids["assessment_id"],
                 "Entry timing under pressure", "TECHNICAL", "DECISION_QUALITY",
                 "{}", "{}", "OPEN", coach, now, now),
            )
            cur.execute(
                """INSERT INTO kaizo_evidence_linked_diagnoses
                   (diagnosis_id,problem_id,athlete_id,assessment_id,evidence_ids,
                    diagnosis,diagnosed_by,confidence,resolution_state,diagnosed_at)
                   VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)""",
                (ids["diagnosis_id"], ids["problem_id"], athlete_id,
                 ids["assessment_id"], evidence_ids, "Entry timing degrades under pressure",
                 coach, "HIGH", "UNRESOLVED", now),
            )
            cur.execute(
                """INSERT INTO kaizo_decision_candidates
                   (candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                    candidate_type,title,rationale,source_diagnosis,status,generated_by,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (ids["candidate_id"], ids["diagnosis_id"], ids["problem_id"], athlete_id,
                 ids["assessment_id"], "DIRECT_INTERVENTION", "Improve entry timing",
                 "Use a verified drill progression", "Entry timing diagnosis",
                 "PENDING_COACH_REVIEW", coach, now),
            )
            cur.execute(
                """INSERT INTO kaizo_coach_decision_reviews
                   (review_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                    action,status,coach_id,override_reason,reviewed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (ids["review_id"], ids["candidate_id"], ids["diagnosis_id"],
                 ids["problem_id"], athlete_id, ids["assessment_id"],
                 "CONFIRM", "CONFIRMED", coach, None, now),
            )
            cur.execute(
                """INSERT INTO kaizo_decision_records
                   (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                    candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (ids["decision_id"], ids["candidate_id"], ids["diagnosis_id"],
                 ids["problem_id"], athlete_id, ids["assessment_id"],
                 "DIRECT_INTERVENTION", "CONFIRM", coach,
                 "Improve entry timing under pressure", "RETEST", "RECORDED", now),
            )
            cur.execute(
                """INSERT INTO kaizo_training_plans
                   (plan_id,athlete_id,decision_id,title,objective,constraints,status,created_by,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                (ids["plan_id"], athlete_id, ids["decision_id"],
                 "Entry timing plan", "Improve stable entry timing", "{}",
                 "DRAFT", coach, now),
            )
            cur.execute(
                """INSERT INTO kaizo_training_sessions
                   (session_id,plan_id,athlete_id,title,duration_minutes,blocks,status,created_by,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                (ids["session_id"], ids["plan_id"], athlete_id,
                 "Entry timing session", 10,
                 json.dumps([{"name": "uchi-komi", "duration_minutes": 10}]),
                 "DRAFT", coach, now),
            )
            drill_payload = {
                "drill_id": ids["drill_id"], "name": "Entry timing under pressure",
                "evidence": [ids["evidence_id"]], "source": [],
                "coach_review": True, "execution_authorized": False,
            }
            cur.execute(
                """INSERT INTO kaizo_coach_drill_library
                   (drill_id,tenant_id,coach_actor_id,source_assessment_id,payload,status,
                    coach_review,created_by,approved_by,approved_at,created_at,updated_at)
                   VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)""",
                (ids["drill_id"], tenant, coach, ids["assessment_id"],
                 json.dumps(drill_payload), "PUBLISHED", True, coach, coach, now, now, now),
            )
            cur.execute(
                """INSERT INTO kaizo_coach_problem_drill_links
                   (link_id,tenant_id,coach_actor_id,problem_id,drill_id,athlete_id,
                    assessment_id,rationale,evidence_ids,created_by,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                (ids["link_id"], tenant, coach, ids["problem_id"], ids["drill_id"],
                 athlete_id, ids["assessment_id"], "Drill addresses the diagnosed problem",
                 evidence_ids, coach, now),
            )
    return ids


def _create_owned_scope(label: str):
    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name=label,
    )
    return tenant, coach, athlete["athlete_id"], {
        "X-KAIZO-Actor": coach, "X-KAIZO-Role": "coach", "X-KAIZO-Tenant": tenant,
    }


def _complete_workflow(ids, athlete_id, headers):
    decision = ids["decision_id"]
    session = ids["session_id"]
    drill = ids["drill_id"]
    evidence = ids["evidence_id"]
    results = {}

    results["033"] = client.post(
        "/api/v1/training-workflow/feat-033/decision-drill",
        json={"athlete_id": athlete_id, "decision_id": decision, "drill_id": drill,
              "rationale": "Targets entry timing", "evidence_refs": [evidence],
              "coach_final_authority": False, "selected_by": "SPOOFED-CLIENT-IDENTITY"},
        headers=headers,
    )
    assert results["033"].status_code == 201, results["033"].text

    results["034"] = client.post(
        "/api/v1/training-workflow/feat-034/drill-prescription",
        json={"athlete_id": athlete_id, "decision_id": decision, "session_id": session,
              "selection_record_id": results["033"].json()["record_id"],
              "drill_id": drill, "objective": "Improve entry timing",
              "dosage": {"sets": 3, "reps": 5}, "prescribed_by": "SPOOFED-CLIENT-IDENTITY"},
        headers=headers,
    )
    assert results["034"].status_code == 201, results["034"].text

    results["035"] = client.post(
        "/api/v1/training-workflow/feat-035/execution-cues",
        json={"athlete_id": athlete_id, "session_id": session,
              "prescription_record_id": results["034"].json()["record_id"],
              "drill_id": drill, "cues": ["Elbow close", "Enter under balance"],
              "checklist": ["Grip secured", "Posture stable"]},
        headers=headers,
    )
    assert results["035"].status_code == 201, results["035"].text

    results["036"] = client.post(
        "/api/v1/training-workflow/feat-036/training-response",
        json={"athlete_id": athlete_id, "session_id": session,
              "cue_record_id": results["035"].json()["record_id"],
              "response": {"quality": "GOOD"}, "kpi_values": {"entry_success": 5}},
        headers=headers,
    )
    assert results["036"].status_code == 201, results["036"].text

    results["037"] = client.post(
        "/api/v1/training-workflow/feat-037/retest",
        json={"athlete_id": athlete_id, "session_id": session,
              "response_record_id": results["036"].json()["record_id"],
              "baseline_reference": ids["assessment_id"],
              "retest_values": {"entry_success": 6}, "evidence_refs": [evidence]},
        headers=headers,
    )
    assert results["037"].status_code == 201, results["037"].text

    results["038"] = client.post(
        "/api/v1/training-workflow/feat-038/before-after",
        json={"athlete_id": athlete_id, "retest_record_id": results["037"].json()["record_id"],
              "baseline": {"entry_success": 4}, "current": {"entry_success": 6},
              "comparison_method": "absolute_change"},
        headers=headers,
    )
    assert results["038"].status_code == 201, results["038"].text

    results["039"] = client.post(
        "/api/v1/training-workflow/feat-039/progress-state",
        json={"athlete_id": athlete_id,
              "comparison_record_id": results["038"].json()["record_id"],
              "state": {"status": "IMPROVING", "entry_success": 6},
              "evidence_refs": [evidence]},
        headers=headers,
    )
    assert results["039"].status_code == 201, results["039"].text

    results["040"] = client.post(
        "/api/v1/training-workflow/feat-040/next-decision-trigger",
        json={"athlete_id": athlete_id, "session_id": session,
              "progress_record_id": results["039"].json()["record_id"],
              "trigger_type": "RETEST_COMPLETE",
              "trigger_reason": "Retest changed the decision state",
              "required_evidence": [evidence]},
        headers=headers,
    )
    assert results["040"].status_code == 201, results["040"].text
    return {key: response.json() for key, response in results.items()}


def test_workflow_lineage_and_tenant_audit_commit_atomically(monkeypatch):
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant, coach, athlete_id, headers = _create_owned_scope("FEAT-033..040 valid lineage")
    ids = _seed_lineage(tenant, coach, athlete_id)

    def unexpected_request_ddl():
        raise AssertionError("FEAT-033..040 request handlers must not execute schema DDL")

    monkeypatch.setattr(training_workflow, "_ensure_schema", unexpected_request_ddl)
    statements = []
    original_connection = persistence.connection

    class RecordingCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def __enter__(self):
            self.cursor.__enter__()
            return self

        def __exit__(self, *args):
            return self.cursor.__exit__(*args)

        def execute(self, query, params=None):
            statements.append(str(query))
            return self.cursor.execute(query, params)

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    class RecordingConnection:
        def __init__(self, connection):
            self.connection = connection

        def cursor(self):
            return RecordingCursor(self.connection.cursor())

        def __getattr__(self, name):
            return getattr(self.connection, name)

    @contextmanager
    def recording_connection():
        with original_connection() as conn:
            yield RecordingConnection(conn)

    monkeypatch.setattr(persistence, "connection", recording_connection)
    records = _complete_workflow(ids, athlete_id, headers)
    monkeypatch.setattr(persistence, "connection", original_connection)

    assert set(records) == {"033", "034", "035", "036", "037", "038", "039", "040"}
    for feature, record in records.items():
        assert record["created_by"] == coach
        assert record["tenant_id"] == tenant
        assert record["coach_actor_id"] == coach
        assert record["coach_final_authority"] is True
        assert record["execution_authorized"] is False
        assert record["decision_id"] == ids["decision_id"]
        if feature == "033":
            assert record["session_id"] is None
        else:
            assert record["session_id"] == ids["session_id"]

    own_read = client.get(
        f"/api/v1/training-workflow/athletes/{athlete_id}", headers=headers,
    )
    assert own_read.status_code == 200, own_read.text
    assert all(len(own_read.json()["features"][f"FEAT-{number:03d}"]) == 1
               for number in range(33, 41))

    normalized = [query.upper() for query in statements]
    lock_indexes = [
        i for i, query in enumerate(normalized)
        if "FROM KAIZO_COACH_ATHLETE_OWNERSHIP" in query and "FOR UPDATE" in query
    ]
    insert_indexes = [
        i for i, query in enumerate(normalized)
        if "INSERT INTO KAIZO_TRAINING_WORKFLOW_RECORDS" in query
    ]
    assert lock_indexes and insert_indexes, statements
    assert lock_indexes[0] < insert_indexes[0], statements
    assert any("JOIN KAIZO_COACH_ATHLETE_OWNERSHIP" in query for query in normalized), statements
    assert not any(
        query.lstrip().startswith(("CREATE TABLE", "ALTER TABLE", "CREATE INDEX"))
        for query in normalized
    ), statements

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT tenant_id,coach_actor_id,created_by,decision_id,session_id,payload
                   FROM kaizo_training_workflow_records WHERE record_id=%s""",
                (records["033"]["record_id"],),
            )
            stored = cur.fetchone()
            assert stored[:5] == (tenant, coach, coach, ids["decision_id"], None)
            assert stored[5]["coach_final_authority"] is True
            assert stored[5]["execution_authorized"] is False
            assert "selected_by" not in stored[5]
            cur.execute(
                """SELECT who,action,tenant_id FROM kaizo_audit_logs
                   WHERE action='FEAT-033_RECORDED' AND new_value->>'record_id'=%s""",
                (records["033"]["record_id"],),
            )
            assert cur.fetchone() == (coach, "FEAT-033_RECORDED", tenant)

    other_headers = {**headers, "X-KAIZO-Actor": coach + "-OTHER"}
    denied = client.get(
        f"/api/v1/training-workflow/athletes/{athlete_id}", headers=other_headers,
    )
    assert denied.status_code == 404


def test_cross_scope_decision_and_session_references_are_rejected():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant, coach, athlete_id, headers = _create_owned_scope("Primary Coach scope")
    ids = _seed_lineage(tenant, coach, athlete_id)
    other_tenant, other_coach, other_athlete_id, other_headers = _create_owned_scope("Other Coach scope")
    other_ids = _seed_lineage(other_tenant, other_coach, other_athlete_id)

    wrong_decision = client.post(
        "/api/v1/training-workflow/feat-033/decision-drill",
        json={"athlete_id": athlete_id, "decision_id": other_ids["decision_id"],
              "drill_id": other_ids["drill_id"], "rationale": "cross scope",
              "evidence_refs": [other_ids["evidence_id"]]},
        headers=headers,
    )
    assert wrong_decision.status_code == 404

    selection = client.post(
        "/api/v1/training-workflow/feat-033/decision-drill",
        json={"athlete_id": athlete_id, "decision_id": ids["decision_id"],
              "drill_id": ids["drill_id"], "rationale": "valid selection",
              "evidence_refs": [ids["evidence_id"]]},
        headers=headers,
    )
    assert selection.status_code == 201, selection.text
    wrong_session = client.post(
        "/api/v1/training-workflow/feat-034/drill-prescription",
        json={"athlete_id": athlete_id, "decision_id": ids["decision_id"],
              "session_id": other_ids["session_id"],
              "selection_record_id": selection.json()["record_id"],
              "drill_id": ids["drill_id"], "objective": "Must not cross athlete lineage",
              "dosage": {"sets": 3, "reps": 5}},
        headers=headers,
    )
    assert wrong_session.status_code == 404

    # A valid workflow under the other Coach cannot be used as this Coach's retest parent.
    other_records = _complete_workflow(other_ids, other_athlete_id, other_headers)
    foreign_retest = client.post(
        "/api/v1/training-workflow/feat-038/before-after",
        json={"athlete_id": athlete_id, "retest_record_id": other_records["037"]["record_id"],
              "baseline": {"entry_success": 4}, "current": {"entry_success": 6},
              "comparison_method": "absolute_change"},
        headers=headers,
    )
    assert foreign_retest.status_code == 404


def test_audit_failure_rolls_back_workflow_record():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant, coach, athlete_id, headers = _create_owned_scope("FEAT-033 atomic rollback")
    ids = _seed_lineage(tenant, coach, athlete_id)
    trigger = "kaizo_test_reject_workflow_audit"
    function = "kaizo_test_reject_workflow_audit_fn"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
            cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            cur.execute(f"""
                CREATE FUNCTION {function}() RETURNS trigger AS $$
                BEGIN
                    IF NEW.action = 'FEAT-033_RECORDED' THEN
                        RAISE EXCEPTION 'intentional test audit failure';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            cur.execute(f"""
                CREATE TRIGGER {trigger}
                BEFORE INSERT ON kaizo_audit_logs
                FOR EACH ROW EXECUTE FUNCTION {function}()
            """)
        conn.commit()

    try:
        response = client.post(
            "/api/v1/training-workflow/feat-033/decision-drill",
            json={"athlete_id": athlete_id, "decision_id": ids["decision_id"],
                  "drill_id": ids["drill_id"], "rationale": "Audit failure must roll back",
                  "evidence_refs": [ids["evidence_id"]]},
            headers=headers,
        )
        assert response.status_code == 500
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT count(*) FROM kaizo_training_workflow_records
                       WHERE athlete_id=%s AND feature_id='FEAT-033'
                         AND decision_id=%s AND tenant_id=%s AND coach_actor_id=%s""",
                    (athlete_id, ids["decision_id"], tenant, coach),
                )
                assert cur.fetchone()[0] == 0
                cur.execute(
                    """SELECT count(*) FROM kaizo_audit_logs
                       WHERE action='FEAT-033_RECORDED' AND tenant_id=%s
                         AND new_value->>'decision_id'=%s""",
                    (tenant, ids["decision_id"]),
                )
                assert cur.fetchone()[0] == 0
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
                cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            conn.commit()
