"""Regression tests for durable academy and guardian-consent enforcement."""
from contextlib import contextmanager
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from productization import resource_authorization as access


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.query = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params or ()

    def fetchone(self):
        if "FROM kaizo_academy_assignments" in self.query:
            return (1,) if self.state.get("assignment") else None
        if "FROM kaizo_guardian_links" in self.query:
            return (1,) if self.state.get("guardian_link") else None
        if "FROM kaizo_minor_consents" in self.query:
            return self.state.get("consent")
        return None


class FakeConnection:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return FakeCursor(self.state)

    def commit(self):
        pass


def configure_db(monkeypatch, state):
    monkeypatch.setattr(access.persistence, "is_postgres_enabled", lambda: True)

    @contextmanager
    def connection():
        yield FakeConnection(state)

    monkeypatch.setattr(access.persistence, "connection", connection)
    monkeypatch.setattr(access, "_schema_ready", False)


def test_athlete_must_have_active_assignment_in_requested_academy(monkeypatch):
    configure_db(monkeypatch, {"assignment": False})
    with pytest.raises(access.ResourceAuthorizationError, match="not assigned"):
        access.require_athlete_academy("athlete-1", "academy-A")


def test_parent_access_denied_without_verified_guardian_link(monkeypatch):
    configure_db(monkeypatch, {"guardian_link": False})
    with pytest.raises(access.ResourceAuthorizationError, match="guardian-to-child link"):
        access.require_parent_consent("guardian-1", "athlete-1", "academy-A")


def test_parent_access_denied_when_consent_is_missing(monkeypatch):
    configure_db(monkeypatch, {"guardian_link": True, "consent": None})
    with pytest.raises(access.ResourceAuthorizationError, match="consent is absent"):
        access.require_parent_consent("guardian-1", "athlete-1", "academy-A")


def test_parent_access_denied_when_consent_is_revoked(monkeypatch):
    configure_db(monkeypatch, {"guardian_link": True, "consent": ("revoked", None)})
    with pytest.raises(access.ResourceAuthorizationError, match="not active"):
        access.require_parent_consent("guardian-1", "athlete-1", "academy-A")


def test_parent_access_denied_when_consent_scope_is_not_found(monkeypatch):
    configure_db(monkeypatch, {"guardian_link": True, "consent": None})
    with pytest.raises(access.ResourceAuthorizationError):
        access.require_parent_consent(
            "guardian-1", "athlete-1", "academy-A",
            resource="competition_results", action="export",
        )


def test_parent_access_allows_only_active_unexpired_exact_scope(monkeypatch):
    configure_db(monkeypatch, {
        "guardian_link": True,
        "consent": ("active", "2099-01-01T00:00:00+00:00"),
    })
    access.require_parent_consent(
        "guardian-1", "athlete-1", "academy-A",
        resource="athlete_progress", action="read",
    )


def test_database_unavailable_fails_closed(monkeypatch):
    monkeypatch.setattr(access, "_schema_ready", False)
    monkeypatch.setattr(access.persistence, "is_postgres_enabled", lambda: False)
    with pytest.raises(access.ResourceAuthorizationUnavailable, match="requires PostgreSQL"):
        access.require_parent_consent("guardian-1", "athlete-1", "academy-A")
