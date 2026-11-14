"""FEAT-055 PostgreSQL integration: tenant + Coach + owned-athlete trace scope."""
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
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
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT who,tenant_id,new_value->>'trace_id'
                   FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s
                     AND action='FEAT-055_PRODUCT_ACTION_TRACE_RECORDED'
                     AND new_value->>'trace_id'=%s""",
                (tenant, coach, created["trace_id"]),
            )
            assert cur.fetchone() == (coach, tenant, created["trace_id"])
    assert coach_product_action_traceability.create_coach_product_action_trace(
        tenant_id=tenant, coach_actor_id="OTHER-COACH",
        athlete_id=athlete["athlete_id"], product_action="COACH_REPORT_GENERATED",
        source_record_ids=[str(source_id)], trace_reason="foreign Coach must not write",
    ) is None
    denied = coach_product_action_traceability.list_coach_product_action_traces(
        tenant_id=tenant, coach_actor_id="OTHER-COACH", athlete_id=athlete["athlete_id"]
    )
    assert denied is None


def test_product_action_trace_and_tenant_audit_roll_back_together():
    import pytest

    assert persistence.is_postgres_enabled()
    persistence.initialize()
    state_cycle._ensure_schema()
    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="FEAT-055 rollback"
    )
    history = coach_action_history.get_coach_action_history(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"]
    )
    source = next(
        item["source_record_id"] for item in history["items"]
        if item.get("actor_attribution_verified") is True
        and item.get("source_record_id") is not None
    )
    trigger = "kaizo_test_reject_feat055_audit_" + uuid4().hex[:12]
    function = trigger + "_fn"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
            cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            cur.execute(f"""
                CREATE FUNCTION {function}() RETURNS trigger AS $$
                BEGIN
                    IF NEW.action='FEAT-055_PRODUCT_ACTION_TRACE_RECORDED' THEN
                        RAISE EXCEPTION 'intentional FEAT-055 audit failure';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            cur.execute(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON kaizo_audit_logs "
                f"FOR EACH ROW EXECUTE FUNCTION {function}()"
            )
        conn.commit()
    try:
        with pytest.raises(Exception, match="intentional FEAT-055 audit failure"):
            coach_product_action_traceability.create_coach_product_action_trace(
                tenant_id=tenant, coach_actor_id=coach,
                athlete_id=athlete["athlete_id"],
                product_action="COACH_REPORT_GENERATED",
                source_record_ids=[str(source)],
                trace_reason="audit failure must roll back the trace",
            )
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM kaizo_coach_product_action_traces WHERE tenant_id=%s AND athlete_id=%s",
                    (tenant, athlete["athlete_id"]),
                )
                assert cur.fetchone()[0] == 0
                cur.execute(
                    """SELECT COUNT(*) FROM kaizo_audit_logs
                       WHERE tenant_id=%s AND who=%s
                         AND action='FEAT-055_PRODUCT_ACTION_TRACE_RECORDED'
                         AND new_value->>'athlete_id'=%s""",
                    (tenant, coach, athlete["athlete_id"]),
                )
                assert cur.fetchone()[0] == 0
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
                cur.execute(f"DROP FUNCTION IF EXISTS {function}()")
            conn.commit()



def test_trace_history_read_holds_owner_lock_against_concurrent_reassignment(monkeypatch):
    """A trace read must not pass an ownership check then race with transfer."""
    import pytest

    assert persistence.is_postgres_enabled()
    persistence.initialize()
    state_cycle._ensure_schema()
    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="FEAT-055 read race"
    )
    history = coach_action_history.get_coach_action_history(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"]
    )
    source = next(
        item["source_record_id"] for item in history["items"]
        if item.get("actor_attribution_verified") is True
        and item.get("source_record_id") is not None
    )
    created = coach_product_action_traceability.create_coach_product_action_trace(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        product_action="COACH_REPORT_GENERATED",
        source_record_ids=[str(source)], trace_reason="Read must remain inside owner scope",
    )
    assert created and created["status"] == "TRACE_RECORDED"

    owner_deleted = Event()
    allow_transfer_commit = Event()
    transfer_errors = []

    def transfer_owner():
        try:
            with persistence.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """DELETE FROM kaizo_coach_athlete_ownership
                           WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s""",
                        (tenant, coach, athlete["athlete_id"]),
                    )
                owner_deleted.set()
                if not allow_transfer_commit.wait(5):
                    raise AssertionError("timed out waiting to commit ownership transfer")
                conn.commit()
        except Exception as exc:
            transfer_errors.append(exc)

    transfer_thread = Thread(target=transfer_owner, daemon=True)
    transfer_thread.start()
    assert owner_deleted.wait(5), "ownership transfer did not acquire its delete lock"

    read_transaction_entered = Event()
    read_done = Event()
    read_result = {}
    original_atomic_transaction = persistence.atomic_transaction

    @contextmanager
    def observed_atomic_transaction():
        with original_atomic_transaction() as conn:
            read_transaction_entered.set()
            yield conn

    monkeypatch.setattr(persistence, "atomic_transaction", observed_atomic_transaction)

    def read_history():
        try:
            read_result["value"] = coach_product_action_traceability.list_coach_product_action_traces(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"]
            )
        except Exception as exc:
            read_result["error"] = exc
        finally:
            read_done.set()

    reader_thread = Thread(target=read_history, daemon=True)
    reader_thread.start()
    assert read_transaction_entered.wait(5), "trace read did not start its scoped transaction"
    time.sleep(0.15)
    assert not read_done.is_set(), "trace read escaped while ownership transfer held the row lock"

    allow_transfer_commit.set()
    transfer_thread.join(5)
    reader_thread.join(5)
    assert not transfer_thread.is_alive(), "ownership transfer did not finish"
    assert not reader_thread.is_alive(), "trace read did not finish after ownership transfer"
    assert not transfer_errors, transfer_errors
    assert "error" not in read_result, read_result.get("error")
    assert read_result["value"] is None
