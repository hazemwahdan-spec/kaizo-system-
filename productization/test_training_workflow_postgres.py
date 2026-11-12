"""PostgreSQL acceptance for atomic, tenant-scoped FEAT-033..040 workflow writes."""
import os
import sys
import json
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
            cur.execute("""INSERT INTO kaizo_audit_logs
                (timestamp,who,action,old_value,new_value,why,tenant_id)
                VALUES (%s,%s,'COACH_DECISION_RECORD_RECORDED',NULL,%s::jsonb,
                        'Protected Coach decision source for FEAT-033',%s)""",
                (now,coach,json.dumps({"decision_id":decision,"athlete_id":athlete_id,
                                       "coach_id":coach,"problem_id":problem,"status":"RECORDED"}),tenant))
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
    assert record["payload"]["problem_id"]
    assert record["payload"]["problem_drill_link_id"]

    athlete_id = athlete["athlete_id"]
    session_id = "SESSION-" + uuid4().hex
    def post(feature, suffix, body):
        result = client.post(f"/api/v1/training-workflow/feat-{feature}/{suffix}",
                             json={"athlete_id":athlete_id, **body}, headers=headers)
        assert result.status_code == 201, (feature, result.text)
        saved = result.json()
        assert saved["decision_id"] == decision_id
        assert saved["session_id"] == session_id
        assert saved["tenant_id"] == tenant and saved["coach_actor_id"] == coach
        assert saved["execution_authorized"] is False
        return saved

    prescription = post("034","drill-prescription",{
        "decision_id":decision_id,"session_id":session_id,"drill_id":drill_id,
        "objective":"Improve entry timing","dosage":{"sets":3,"reps":5}})
    cues = post("035","execution-cues",{
        "session_id":session_id,"drill_id":drill_id,
        "cues":["Elbow close"],"checklist":["Posture stable"]})
    training_response = post("036","training-response",{
        "session_id":session_id,"drill_id":drill_id,
        "prescription_record_id":prescription["record_id"],
        "execution_cue_record_id":cues["record_id"],
        "response":{"quality":"GOOD"},"kpi_values":{"entry_success":4}})
    bad_retest = client.post("/api/v1/training-workflow/feat-037/retest",headers=headers,json={
        "athlete_id":athlete_id,"session_id":session_id,
        "response_record_id":training_response["record_id"],
        "baseline_reference":training_response["record_id"],
        "retest_values":{"different_kpi":6},"evidence_refs":["REF-POSTGRES"]})
    assert bad_retest.status_code == 409, bad_retest.text
    retest = post("037","retest",{
        "session_id":session_id,"response_record_id":training_response["record_id"],
        "baseline_reference":training_response["record_id"],
        "retest_values":{"entry_success":6},"evidence_refs":["REF-POSTGRES"]})
    comparison = post("038","before-after",{
        "response_record_id":training_response["record_id"],"retest_record_id":retest["record_id"],
        "baseline":{"entry_success":4},"current":{"entry_success":6},
        "comparison_method":"same_kpi_absolute_change"})
    progress = post("039","progress-state",{
        "comparison_record_id":comparison["record_id"],"state":{"status":"IMPROVING"},"evidence_refs":["REF-POSTGRES"]})
    trigger = post("040","next-decision-trigger",{
        "session_id":session_id,"progress_record_id":progress["record_id"],
        "trigger_type":"RETEST_COMPLETE","trigger_reason":"Coach reviewed progress",
        "required_evidence":[comparison["record_id"]]})
    assert trigger["record_id"]

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
        "evidence_refs": ["REF-POSTGRES"],
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


def test_oidc_bearer_authenticates_training_workflow_and_ignores_forged_headers(monkeypatch):
    """Exercise the real FEAT-033 route through verified RS256 OIDC and PostgreSQL."""
    assert persistence.is_postgres_enabled()
    persistence.initialize()

    import time
    import jwt
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric import rsa
    from productization import identity

    issuer = "https://issuer.example/"
    audience = "kaizo-api"
    jwks_url = "https://issuer.example/.well-known/jwks.json"
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_OIDC_ISSUER", issuer)
    monkeypatch.setenv("KAIZO_OIDC_AUDIENCE", audience)
    monkeypatch.setenv("KAIZO_OIDC_JWKS_URL", jwks_url)
    monkeypatch.delenv("KAIZO_OIDC_CLAIM_NAMESPACE", raising=False)

    trusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class LocalJWKClient:
        def __init__(self, url):
            assert url == jwks_url

        def get_signing_key_from_jwt(self, token):
            assert jwt.get_unverified_header(token)["kid"] == "local-oidc-test-key"
            return SimpleNamespace(key=trusted_key.public_key())

    monkeypatch.setattr(identity, "PyJWKClient", LocalJWKClient)

    def bearer(actor, tenant, role="coach", signing_key=trusted_key, permissions=("product",)):
        now = int(time.time())
        claims = {
            "sub": actor,
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": now + 300,
            "permissions": list(permissions),
            "https://kaizo.system/kaizo_role": role,
            "https://kaizo.system/tenant_id": tenant,
        }
        token = jwt.encode(
            claims,
            signing_key,
            algorithm="RS256",
            headers={"kid": "local-oidc-test-key"},
        )
        return "Bearer " + token

    tenant = "TENANT-OIDC-" + uuid4().hex
    coach = "auth0|coach-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant,
        coach_actor_id=coach,
        display_name="OIDC FEAT-033 PostgreSQL acceptance",
    )
    decision_id, drill_id = seed_authoritative_feat033_sources(
        tenant, coach, athlete["athlete_id"]
    )
    path = "/api/v1/training-workflow/feat-033/decision-drill"
    payload = {
        "athlete_id": athlete["athlete_id"],
        "decision_id": decision_id,
        "drill_id": drill_id,
        "rationale": "Verified OIDC Coach ownership acceptance",
        "evidence_refs": ["REF-POSTGRES"],
        "selected_by": "FORGED-CLIENT-IDENTITY",
    }

    verified_headers = {
        "Authorization": bearer(coach, tenant),
        "X-KAIZO-Actor": "forged-actor",
        "X-KAIZO-Role": "administrator",
        "X-KAIZO-Tenant": "FORGED-TENANT",
        "X-KAIZO-Resource-Owner": "FORGED-ATHLETE",
    }
    created = client.post(path, json=payload, headers=verified_headers)
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["created_by"] == coach
    assert record["coach_actor_id"] == coach
    assert record["tenant_id"] == tenant
    assert record["execution_authorized"] is False

    own_read = client.get(
        f"/api/v1/training-workflow/athletes/{athlete['athlete_id']}",
        headers={"Authorization": bearer(coach, tenant)},
    )
    assert own_read.status_code == 200, own_read.text
    assert len(own_read.json()["features"]["FEAT-033"]) == 1

    no_product_permission = bearer(coach, tenant, permissions=())
    permission_denied = client.get(
        f"/api/v1/training-workflow/athletes/{athlete['athlete_id']}",
        headers={"Authorization": no_product_permission},
    )
    assert permission_denied.status_code == 403, permission_denied.text

    other_coach = bearer("auth0|other-coach-" + uuid4().hex, tenant)
    other_tenant = bearer("auth0|foreign-tenant-coach-" + uuid4().hex,
                          "TENANT-FOREIGN-" + uuid4().hex)
    non_coach = bearer("auth0|athlete-" + uuid4().hex, tenant, role="athlete")
    invalid_signature = bearer(coach, tenant, signing_key=attacker_key)

    for foreign_token in (other_coach, other_tenant):
        denied_read = client.get(
            f"/api/v1/training-workflow/athletes/{athlete['athlete_id']}",
            headers={"Authorization": foreign_token},
        )
        assert denied_read.status_code == 404, denied_read.text
        denied_write = client.post(
            path, json=payload, headers={"Authorization": foreign_token},
        )
        assert denied_write.status_code == 404, denied_write.text

    assert client.get(
        f"/api/v1/training-workflow/athletes/{athlete['athlete_id']}",
        headers={"Authorization": non_coach},
    ).status_code == 403
    assert client.get(
        f"/api/v1/training-workflow/athletes/{athlete['athlete_id']}",
        headers={"Authorization": invalid_signature},
    ).status_code == 401
