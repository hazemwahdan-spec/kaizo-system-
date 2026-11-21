"""Real PostgreSQL integration test for durable Coach ownership and audit."""
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import persistence
from productization import coach_roster


def test_postgres_persists_single_coach_ownership_and_tenant_audit():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    coach_roster.reset_memory_state()

    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach,
        display_name="Postgres Ownership Integration",
        metadata={"test": "coach-roster"},
    )

    listed = coach_roster.list_owned_athletes(tenant_id=tenant, coach_actor_id=coach)
    assert [item["athlete_id"] for item in listed] == [athlete["athlete_id"]]
    assert coach_roster.get_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"]
    )["display_name"] == "Postgres Ownership Integration"
    assert coach_roster.get_owned_athlete(
        tenant_id=tenant, coach_actor_id="OTHER-COACH", athlete_id=athlete["athlete_id"]
    ) is None
    assert coach_roster.list_owned_athletes(
        tenant_id="OTHER-TENANT", coach_actor_id=coach
    ) == []

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tenant_id, coach_actor_id
                FROM kaizo_coach_athlete_ownership WHERE athlete_id=%s
            """, (athlete["athlete_id"],))
            ownership = cur.fetchone()
            assert ownership == (tenant, coach)
            cur.execute("""
                SELECT action, tenant_id FROM kaizo_audit_logs
                WHERE who=%s AND action='COACH_ATHLETE_CREATED'
                ORDER BY id DESC LIMIT 1
            """, (coach,))
            audit = cur.fetchone()
            assert audit == ("COACH_ATHLETE_CREATED", tenant)


def test_verified_coach_product_api_uses_postgres_and_ignores_spoofed_scope(monkeypatch):
    """A verified Coach route must persist and scope records in PostgreSQL."""
    assert persistence.is_postgres_enabled()
    persistence.initialize()

    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    from fastapi.testclient import TestClient
    from main import app
    from productization import product_api
    from productization.identity import Principal

    tenant_a = "TENANT-" + uuid4().hex
    tenant_b = "TENANT-" + uuid4().hex
    coach_a = "auth0|coach-" + uuid4().hex
    coach_b = "auth0|coach-" + uuid4().hex
    coach_c = "auth0|coach-" + uuid4().hex

    principals = {
        "Bearer coach-a": Principal(
            actor_id=coach_a, role="coach", tenant_id=tenant_a,
            resource_owner_id=None, verified=True, source="oidc_jwt",
            permissions=frozenset({"product"}),
        ),
        "Bearer coach-b": Principal(
            actor_id=coach_b, role="coach", tenant_id=tenant_a,
            resource_owner_id=None, verified=True, source="oidc_jwt",
            permissions=frozenset({"product"}),
        ),
        "Bearer coach-c": Principal(
            actor_id=coach_c, role="coach", tenant_id=tenant_b,
            resource_owner_id=None, verified=True, source="oidc_jwt",
            permissions=frozenset({"product"}),
        ),
    }

    def resolve_bearer(authorization):
        if authorization not in principals:
            raise product_api.IdentityNotConfiguredError("unknown integration-test token")
        return principals[authorization]

    monkeypatch.setattr(product_api, "resolve_bearer_principal", resolve_bearer)
    client = TestClient(app)
    created = client.post(
        "/api/v1/product/coach/athletes",
        headers={
            "Authorization": "Bearer coach-a",
            "X-KAIZO-Actor": "attacker",
            "X-KAIZO-Role": "administrator",
            "X-KAIZO-Tenant": "TENANT-ATTACKER",
        },
        json={"display_name": "Verified PostgreSQL Coach Athlete"},
    )
    assert created.status_code == 201, created.text
    athlete_id = created.json()["athlete_id"]
    assert created.json()["coach_final_authority"] is True
    assert created.json()["execution_authorized"] is False

    owner_read = client.get(
        f"/api/v1/product/coach/athletes/{athlete_id}",
        headers={"Authorization": "Bearer coach-a"},
    )
    assert owner_read.status_code == 200, owner_read.text
    assert owner_read.json()["display_name"] == "Verified PostgreSQL Coach Athlete"

    same_tenant_other_coach = client.get(
        f"/api/v1/product/coach/athletes/{athlete_id}",
        headers={"Authorization": "Bearer coach-b"},
    )
    other_tenant = client.get(
        f"/api/v1/product/coach/athletes/{athlete_id}",
        headers={"Authorization": "Bearer coach-c"},
    )
    assert same_tenant_other_coach.status_code == 404
    assert other_tenant.status_code == 404

    assert client.get(
        "/api/v1/product/coach/athletes",
        headers={"Authorization": "Bearer coach-b"},
    ).json()["total"] == 0
    assert client.get(
        "/api/v1/product/coach/athletes",
        headers={"Authorization": "Bearer coach-c"},
    ).json()["total"] == 0

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tenant_id, coach_actor_id
                FROM kaizo_coach_athlete_ownership
                WHERE athlete_id=%s
                """,
                (athlete_id,),
            )
            assert cur.fetchone() == (tenant_a, coach_a)
            cur.execute(
                """
                SELECT action, tenant_id
                FROM kaizo_audit_logs
                WHERE who=%s AND action='COACH_ATHLETE_CREATED'
                ORDER BY id DESC LIMIT 1
                """,
                (coach_a,),
            )
            assert cur.fetchone() == ("COACH_ATHLETE_CREATED", tenant_a)
