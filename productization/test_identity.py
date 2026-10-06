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


def test_oidc_mode_fails_closed_without_provider_configuration(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    for name in ("KAIZO_OIDC_ISSUER", "KAIZO_OIDC_AUDIENCE", "KAIZO_OIDC_JWKS_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(IdentityNotConfiguredError, match="OIDC production identity"):
        resolve_principal("ignored", "coach", "ignored", None, "Bearer test-token")


def test_oidc_requires_bearer(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("KAIZO_OIDC_AUDIENCE", "kaizo")
    monkeypatch.setenv("KAIZO_OIDC_JWKS_URL", "https://issuer.example/.well-known/jwks.json")
    with pytest.raises(IdentityNotConfiguredError, match="Bearer authentication"):
        resolve_principal("ignored", "coach", "ignored", None, None)
