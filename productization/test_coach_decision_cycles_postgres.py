"""PostgreSQL acceptance for Coach-owned durable decision cycles and atomic audit."""
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import persistence
from productization import coach_roster, coach_decision_cycles


def _owned_scope():
    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach,
        display_name="Decision Cycle PostgreSQL Acceptance",
        metadata={"test": "coach-decision-cycle"},
    )
    return tenant, coach, athlete["athlete_id"]


def test_postgres_decision_cycle_create_adapt_readback_and_scope():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant, coach, athlete_id = _owned_scope()
    case_id = "CASE-" + uuid4().hex
    cycle = coach_decision_cycles.create_cycle(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        case_id=case_id,
        decision_input={"decision": {"choice": "adapt"}, "intervention": {"drill": "seoi"}},
        decision_output={"status": "LOOP_COMPLETED", "coach_final_authority": True},
    )
    cycle_id = cycle["decision_cycle_id"]

    before = coach_decision_cycles.get_owned_cycle(
        decision_cycle_id=cycle_id, tenant_id=tenant,
        coach_actor_id=coach, athlete_id=athlete_id,
    )
    assert before is not None
    assert before["version"] == 1
    assert before["decision_output"]["status"] == "LOOP_COMPLETED"
    assert coach_decision_cycles.get_owned_cycle(
        decision_cycle_id=cycle_id, tenant_id=tenant,
        coach_actor_id="OTHER-COACH", athlete_id=athlete_id,
    ) is None
    assert coach_decision_cycles.get_owned_cycle(
        decision_cycle_id=cycle_id, tenant_id="OTHER-TENANT",
        coach_actor_id=coach, athlete_id=athlete_id,
    ) is None

    adapted = coach_decision_cycles.record_adaptation(
        decision_cycle_id=cycle_id, tenant_id=tenant,
        coach_actor_id=coach, athlete_id=athlete_id, case_id=case_id,
        adaptation_input={"decision_cycle_id": cycle_id, "operation": "individual_adaptation"},
        adaptation_output={"status": "ADAPTED", "scope": "individual"},
    )
    assert adapted is not None
    assert adapted["version"] == 2
    assert adapted["adaptation_output"]["status"] == "ADAPTED"

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT action,tenant_id FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s
                     AND action IN ('COACH_DECISION_CYCLE_CREATED','COACH_DECISION_CYCLE_ADAPTED')
                   ORDER BY action""",
                (tenant, coach),
            )
            events = cur.fetchall()
    assert events == [
        ("COACH_DECISION_CYCLE_ADAPTED", tenant),
        ("COACH_DECISION_CYCLE_CREATED", tenant),
    ]


def test_postgres_decision_cycle_and_audit_rollback_together():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant, coach, athlete_id = _owned_scope()
    trigger = "fail_cycle_audit_" + uuid4().hex
    function = "fail_cycle_audit_fn_" + uuid4().hex
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE FUNCTION {function}() RETURNS trigger AS $$
                BEGIN
                    IF NEW.action = 'COACH_DECISION_CYCLE_CREATED'
                       AND NEW.tenant_id = '{tenant}' THEN
                        RAISE EXCEPTION 'forced decision-cycle audit failure';
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
    try:
        try:
            coach_decision_cycles.create_cycle(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                case_id="CASE-ROLLBACK-" + uuid4().hex,
                decision_input={"decision": {"choice": "hold"}},
                decision_output={"status": "HOLD"},
            )
        except Exception as exc:
            assert "forced decision-cycle audit failure" in str(exc)
        else:
            raise AssertionError("expected the audit trigger to abort cycle creation")

        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM kaizo_coach_decision_cycles WHERE tenant_id=%s",
                    (tenant,),
                )
                cycle_count = cur.fetchone()[0]
                cur.execute(
                    """SELECT COUNT(*) FROM kaizo_audit_logs
                       WHERE tenant_id=%s AND action='COACH_DECISION_CYCLE_CREATED'""",
                    (tenant,),
                )
                audit_count = cur.fetchone()[0]
        assert cycle_count == 0
        assert audit_count == 0
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TRIGGER IF EXISTS {trigger} ON kaizo_audit_logs")
                cur.execute(f"DROP FUNCTION IF EXISTS {function}()")



def test_postgres_decision_cycle_create_rechecks_owner_inside_write_transaction():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant, coach, athlete_id = _owned_scope()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s""",
                (tenant, coach, athlete_id),
            )

    cycle = coach_decision_cycles.create_cycle(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        case_id="CASE-OWNER-LOST-" + uuid4().hex,
        decision_input={"decision": {"choice": "retain"}},
        decision_output={"status": "RECORDED"},
    )
    assert cycle is None
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_coach_decision_cycles
                   WHERE tenant_id=%s AND athlete_id=%s""",
                (tenant, athlete_id),
            )
            assert cur.fetchone()[0] == 0
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s
                     AND action='COACH_DECISION_CYCLE_CREATED'""",
                (tenant, coach),
            )
            assert cur.fetchone()[0] == 0


def test_postgres_adaptation_rechecks_owner_and_case_before_atomic_write():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant, coach, athlete_id = _owned_scope()
    case_id = "CASE-ADAPT-OWNER-LOST-" + uuid4().hex
    cycle = coach_decision_cycles.create_cycle(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        case_id=case_id,
        decision_input={"decision": {"choice": "adapt"}},
        decision_output={"status": "RECORDED"},
    )
    cycle_id = cycle["decision_cycle_id"]
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s""",
                (tenant, coach, athlete_id),
            )

    adapted = coach_decision_cycles.record_adaptation(
        decision_cycle_id=cycle_id, tenant_id=tenant,
        coach_actor_id=coach, athlete_id=athlete_id, case_id=case_id,
        adaptation_input={"decision_cycle_id": cycle_id},
        adaptation_output={"status": "ADAPTED"},
    )
    assert adapted is None
    assert coach_decision_cycles.get_owned_cycle(
        decision_cycle_id=cycle_id, tenant_id=tenant,
        coach_actor_id=coach, athlete_id=athlete_id,
    ) is None
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT version,adaptation_input,adaptation_output
                   FROM kaizo_coach_decision_cycles WHERE decision_cycle_id=%s""",
                (cycle_id,),
            )
            assert cur.fetchone() == (1, None, None)
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s
                     AND action='COACH_DECISION_CYCLE_ADAPTED'""",
                (tenant, coach),
            )
            assert cur.fetchone()[0] == 0
