"""PostgreSQL acceptance for atomic, tenant-scoped FEAT-033..040 workflow writes."""
import os
import sys
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4

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


def seed_authoritative_feat033_sources(tenant, coach, athlete_id):
    decision = "DEC-" + uuid4().hex
    problem = "PROB-" + uuid4().hex
    assessment = "ASSESS-" + uuid4().hex
    drill = "DRILL-" + uuid4().hex
    link = "LINK-" + uuid4().hex
    now = "2026-11-10T00:00:00+00:00"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO kaizo_problem_statements
                (problem_id,athlete_id,assessment_id,statement,problem_type,impact,
                 context,structured_fields,status,created_by,created_at,updated_at)
                VALUES (%s,%s,%s,'Entry timing problem','TECHNICAL','MEDIUM',
                        '{}'::jsonb,'{}'::jsonb,'ACTIVE',%s,%s,%s)""",
                (problem,athlete_id,assessment,coach,now,now))
            cur.execute("""INSERT INTO kaizo_decision_records
                (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                 candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                VALUES (%s,%s,%s,%s,%s,%s,'TECHNICAL_ADAPTATION','CONFIRM',%s,
                        'Improve entry timing','Increase successful entries','RECORDED',%s)""",
                (decision,"CAND-"+uuid4().hex,"DIAG-"+uuid4().hex,problem,athlete_id,
                 assessment,coach,now))
            cur.execute("""INSERT INTO kaizo_coach_drill_library
                (drill_id,tenant_id,coach_actor_id,source_assessment_id,payload,status,
                 coach_review,created_by,approved_by,approved_at,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,'PUBLISHED',TRUE,%s,%s,%s,%s,%s)""",
                (drill,tenant,coach,assessment,
                 '{"name":"Entry timing drill","coach_review":true}',
                 coach,coach,now,now,now))
            cur.execute("""INSERT INTO kaizo_coach_problem_drill_links
                (link_id,tenant_id,coach_actor_id,problem_id,drill_id,athlete_id,
                 assessment_id,rationale,evidence_ids,created_by,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'Targets recorded decision','["REF-POSTGRES"]'::jsonb,%s,%s)""",
                (link,tenant,coach,problem,drill,athlete_id,assessment,coach,now))
        conn.commit()
    return decision, drill


def test_workflow_record_and_tenant_audit_commit_atomically(monkeypatch):
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach,
        display_name="FEAT-033 workflow PostgreSQL acceptance",
    )
    headers = {
        "X-KAIZO-Actor": coach,
        "X-KAIZO-Role": "coach",
        "X-KAIZO-Tenant": tenant,
    }
    decision_id, drill_id = seed_authoritative_feat033_sources(tenant, coach, athlete["athlete_id"])
    payload = {
        "athlete_id": athlete["athlete_id"],
        "decision_id": decision_id,
        "drill_id": drill_id,
        "rationale": "PostgreSQL ownership and audit acceptance",
        "evidence_refs": ["REF-POSTGRES"],
        "selected_by": "SPOOFED-CLIENT-IDENTITY",
    }
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
    response = client.post(
        "/api/v1/training-workflow/feat-033/decision-drill",
        json=payload, headers=headers,
    )
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["created_by"] == coach
    assert record["tenant_id"] == tenant
    assert record["coach_actor_id"] == coach

    own_read = client.get(
        f"/api/v1/training-workflow/athletes/{athlete['athlete_id']}",
        headers=headers,
    )
    assert own_read.status_code == 200, own_read.text
    monkeypatch.setattr(persistence, "connection", original_connection)

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
                """SELECT tenant_id, coach_actor_id, created_by
                   FROM kaizo_training_workflow_records WHERE record_id=%s""",
                (record["record_id"],),
            )
            stored = cur.fetchone()
            assert stored == (tenant, coach, coach)
            cur.execute(
                """SELECT who, action, tenant_id FROM kaizo_audit_logs
                   WHERE action='FEAT-033_RECORDED' AND new_value->>'record_id'=%s""",
                (record["record_id"],),
            )
            audit = cur.fetchone()
            assert audit == (coach, "FEAT-033_RECORDED", tenant)

    # A different Coach cannot read the record, even in the same tenant.
    other_headers = {**headers, "X-KAIZO-Actor": coach + "-OTHER"}
    denied = client.get(
        f"/api/v1/training-workflow/athletes/{athlete['athlete_id']}",
        headers=other_headers,
    )
    assert denied.status_code == 404


def test_audit_failure_rolls_back_workflow_record():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach,
        display_name="FEAT-033 atomic rollback acceptance",
    )
    headers = {
        "X-KAIZO-Actor": coach,
        "X-KAIZO-Role": "coach",
        "X-KAIZO-Tenant": tenant,
    }
    decision_id, drill_id = seed_authoritative_feat033_sources(tenant, coach, athlete["athlete_id"])
    payload = {
        "athlete_id": athlete["athlete_id"],
        "decision_id": decision_id,
        "drill_id": drill_id,
        "rationale": "Audit failure must roll back record",
        "evidence_refs": ["REF-ROLLBACK"],
    }
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
            json=payload, headers=headers,
        )
        assert response.status_code == 500
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT count(*) FROM kaizo_training_workflow_records
                       WHERE athlete_id=%s AND decision_id=%s""",
                    (athlete["athlete_id"], payload["decision_id"]),
                )
                assert cur.fetchone()[0] == 0
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
                cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            conn.commit()
