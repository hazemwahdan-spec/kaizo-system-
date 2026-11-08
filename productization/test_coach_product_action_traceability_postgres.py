"""FEAT-055 PostgreSQL integration: tenant + Coach + owned-athlete trace scope."""
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import persistence
import state_cycle
from productization import coach_roster, coach_action_history, coach_product_action_traceability


def test_product_action_trace_is_durable_and_scoped_to_verified_coach():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    state_cycle._ensure_schema()
    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="FEAT-055 trace"
    )
    history = coach_action_history.get_coach_action_history(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"]
    )
    assert history and history["available"]
    verified_items = [
        item for item in history["items"]
        if item.get("actor_attribution_verified") is True
        and item.get("source_record_id") is not None
    ]
    assert verified_items, "PostgreSQL history must expose a verified actor-attributed source"
    source_id = verified_items[0]["source_record_id"]
    created = coach_product_action_traceability.create_coach_product_action_trace(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        product_action="COACH_REPORT_GENERATED",
        source_record_ids=[str(source_id)], trace_reason="Link report to verified source event"
    )
    assert created and created["status"] == "TRACE_RECORDED"
    assert created["source_scope_verified"] is True
    own = coach_product_action_traceability.list_coach_product_action_traces(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"]
    )
    assert own and own["total"] == 1
    assert own["items"][0]["trace_id"] == created["trace_id"]
    denied = coach_product_action_traceability.list_coach_product_action_traces(
        tenant_id=tenant, coach_actor_id="OTHER-COACH", athlete_id=athlete["athlete_id"]
    )
    assert denied is None
