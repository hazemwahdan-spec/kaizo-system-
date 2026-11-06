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
