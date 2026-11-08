"""PostgreSQL acceptance for atomic, tenant-scoped FEAT-033..040 workflow writes."""
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

os.environ["KAIZO_IDENTITY_MODE"] = "development"
os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"

from fastapi import FastAPI
from fastapi.testclient import TestClient

import persistence
from productization import coach_roster
from training_workflow import router

app = FastAPI()
app.include_router(router)
client = TestClient(app, raise_server_exceptions=False)


def test_workflow_record_and_tenant_audit_commit_atomically():
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
    payload = {
        "athlete_id": athlete["athlete_id"],
        "decision_id": "DEC-" + uuid4().hex,
        "drill_id": "DRILL-POSTGRES",
        "rationale": "PostgreSQL ownership and audit acceptance",
        "evidence_refs": ["REF-POSTGRES"],
        "selected_by": "SPOOFED-CLIENT-IDENTITY",
    }
    response = client.post(
        "/api/v1/training-workflow/feat-033/decision-drill",
        json=payload, headers=headers,
    )
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["created_by"] == coach
    assert record["tenant_id"] == tenant
    assert record["coach_actor_id"] == coach

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
    payload = {
        "athlete_id": athlete["athlete_id"],
        "decision_id": "DEC-" + uuid4().hex,
        "drill_id": "DRILL-ROLLBACK",
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
