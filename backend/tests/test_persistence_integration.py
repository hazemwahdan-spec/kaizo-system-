import os

import persistence


def test_postgres_persistence_roundtrip():
    assert persistence.is_postgres_enabled()
    persistence.initialize()

    persistence.upsert_knowledge(
        "TEST-ITEM-001",
        {"content": "integration-test", "source": "github-actions"},
        "2026-09-30T00:00:00",
    )
    loaded = persistence.load_knowledge()
    assert loaded["TEST-ITEM-001"]["content"] == "integration-test"

    persistence.upsert_digital_twin(
        {
            "entity_id": "TEST-ATHLETE-001",
            "version": 1,
            "state": {"grip": "validated"},
            "source_event": "TEST_SYNC",
            "case_id": "TEST-CASE-001",
            "updated_at": "2026-09-30T00:00:00",
        }
    )
    twin = persistence.get_digital_twin("TEST-ATHLETE-001")
    assert twin["version"] == 1
    assert twin["state"]["grip"] == "validated"

    persistence.append_audit(
        timestamp="2026-09-30T00:00:00",
        who="integration-test",
        action="TEST_PERSISTENCE",
        old_value=None,
        new_value={"ok": True},
        why="roundtrip verification",
    )
    logs = persistence.list_audit_logs()
    assert any(log["action"] == "TEST_PERSISTENCE" for log in logs)

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE kaizo_audit_logs, kaizo_digital_twin_state, kaizo_knowledge_repository")
        conn.commit()
