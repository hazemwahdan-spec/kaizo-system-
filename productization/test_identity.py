import pytest

from productization.identity import IdentityNotConfiguredError, resolve_principal


def test_development_headers_are_explicitly_unverified(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    principal = resolve_principal("coach-1", "coach", "academy-a", "athlete-1")
    assert principal.verified is False
    assert principal.source == "development_headers"


def test_production_identity_fails_closed(monkeypatch):
    monkeypatch.delenv("KAIZO_IDENTITY_MODE", raising=False)
    with pytest.raises(IdentityNotConfiguredError, match="fail-closed"):
        resolve_principal("coach-1", "coach", "academy-a", "athlete-1")


def test_unknown_role_is_rejected_in_development(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    with pytest.raises(IdentityNotConfiguredError):
        resolve_principal("x", "admin", "academy-a", None)
