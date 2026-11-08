"""Regression: Coach read paths must never execute schema or data writes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

import persistence
from productization import coach_roster, coach_groups
import training_workflow
import state_cycle


class RecordingCursor:
    def __init__(self):
        self.last_query = ""
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.last_query = str(query).strip()
        self.queries.append(self.last_query)
        normalized = self.last_query.upper()
        assert normalized.startswith("SELECT"), (
            "Read path issued a non-SELECT statement: " + self.last_query[:180]
        )

    def fetchone(self):
        if "FROM kaizo_athletes a" in self.last_query:
            return ("athlete-1", "Read-only athlete", "ACTIVE", {}, "created", "updated")
        return None

    def fetchall(self):
        return []


class RecordingConnection:
    def __init__(self):
        self.cursor_instance = RecordingCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        raise AssertionError("A read path must not commit a transaction")


def test_coach_read_paths_issue_select_only_and_never_initialize_schema(monkeypatch):
    connections = []

    def connect():
        connection = RecordingConnection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(persistence, "connection", connect)

    assert coach_roster.get_owned_athlete(
        tenant_id="tenant-1", coach_actor_id="coach-1", athlete_id="athlete-1"
    ) is not None
    assert coach_roster.list_owned_athletes(
        tenant_id="tenant-1", coach_actor_id="coach-1"
    ) == []
    assert coach_roster.list_owned_athlete_status_history(
        tenant_id="tenant-1", coach_actor_id="coach-1", athlete_id="athlete-1"
    ) == []
    assert coach_roster.list_owned_athlete_decision_cycles(
        tenant_id="tenant-1", coach_actor_id="coach-1", athlete_id="athlete-1"
    ) == []
    assert coach_groups.list_groups(
        tenant_id="tenant-1", coach_actor_id="coach-1"
    ) == []
    assert training_workflow._list("FEAT-036", "athlete-1", "tenant-1", "coach-1") == []
    principal = state_cycle._common_headers(
        None, "coach-1", "coach", "tenant-1", None, "athlete-1"
    )
    assert state_cycle.get_state_history(
        "athlete-1", actor_id="coach-1", role="coach", tenant_id="tenant-1"
    )["versions"] == []
    assert state_cycle._latest_link(
        decision_id="decision-1", athlete_id="athlete-1", principal=principal
    ) is None

    all_queries = [query for connection in connections for query in connection.cursor_instance.queries]
    assert all_queries, "The regression must exercise database read paths"
    assert all(query.upper().startswith("SELECT") for query in all_queries)
