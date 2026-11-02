"""Read-only health reporting for durable PostgreSQL readiness."""
from unittest.mock import MagicMock

import persistence
from main import health_check


def test_health_reports_durable_storage_disabled_in_memory_mode(monkeypatch):
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: False)
    result = health_check()
    assert result["status"] == "Online"
    assert result["durable_storage"] == "disabled"


def test_health_reports_durable_storage_available_after_read_only_probe(monkeypatch):
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    connection = MagicMock()
    connection.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
    monkeypatch.setattr(persistence, "connection", lambda: connection)

    result = health_check()

    assert result["durable_storage"] == "available"
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.execute.assert_called_once_with("SELECT 1")


def test_health_reports_durable_storage_unavailable_without_leaking_error(monkeypatch):
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(persistence, "connection", lambda: RaisingContext())

    result = health_check()

    assert result["status"] == "Online"
    assert result["durable_storage"] == "unavailable"
    assert "DATABASE_URL" not in str(result)
    assert "secret" not in str(result).lower()


class RaisingContext:
    def __enter__(self):
        raise RuntimeError("connection failed: secret DATABASE_URL")

    def __exit__(self, *_args):
        return False
