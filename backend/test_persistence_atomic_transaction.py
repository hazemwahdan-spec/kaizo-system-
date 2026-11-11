"""PostgreSQL regression for nested persistence helpers inside one transaction."""
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import persistence


def test_nested_persistence_commit_is_deferred_to_outer_transaction():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    cycle_id = "TX-ROLLBACK-" + uuid4().hex
    tenant_id = "TENANT-" + uuid4().hex
    try:
        try:
            with persistence.atomic_transaction():
                with persistence.connection() as nested:
                    with nested.cursor() as cur:
                        cur.execute(
                            """INSERT INTO kaizo_coach_decision_cycles
                               (decision_cycle_id,tenant_id,coach_actor_id,athlete_id,case_id,
                                decision_input,decision_output,status,version,created_at,updated_at)
                               VALUES (%s,%s,%s,%s,%s,'{}'::jsonb,'{}'::jsonb,'TEST',1,'now','now')""",
                            (cycle_id, tenant_id, "COACH-TX", "ATHLETE-TX", "CASE-TX"),
                        )
                    # Existing persistence helpers call commit(); inside the outer
                    # transaction this must not commit independently.
                    nested.commit()
                raise RuntimeError("force outer rollback")
        except RuntimeError as exc:
            assert "force outer rollback" in str(exc)

        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM kaizo_coach_decision_cycles WHERE decision_cycle_id=%s",
                    (cycle_id,),
                )
                assert cur.fetchone()[0] == 0
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM kaizo_coach_decision_cycles WHERE decision_cycle_id=%s",
                    (cycle_id,),
                )
