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


def test_oidc_mode_rejects_invalid_token_with_default_trust_configuration(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    for name in ("KAIZO_OIDC_ISSUER", "KAIZO_OIDC_AUDIENCE", "KAIZO_OIDC_JWKS_URL"):
        monkeypatch.delenv(name, raising=False)
    # The production Auth0 issuer, audience, and JWKS endpoint have safe,
    # pinned defaults. A malformed token must still fail closed during JWT
    # verification; absent optional overrides do not disable verification.
    with pytest.raises(IdentityNotConfiguredError, match="OIDC token verification failed"):
        resolve_principal("ignored", "coach", "ignored", None, "Bearer test-token")


def test_oidc_requires_bearer(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("KAIZO_OIDC_AUDIENCE", "kaizo")
    monkeypatch.setenv("KAIZO_OIDC_JWKS_URL", "https://issuer.example/.well-known/jwks.json")
    with pytest.raises(IdentityNotConfiguredError, match="Bearer authentication"):
        resolve_principal("ignored", "coach", "ignored", None, None)


def test_namespaced_auth0_claims_resolve_global_publisher():
    from productization.identity import _claims_to_principal

    principal = _claims_to_principal({
        "sub": "auth0|approved-publisher",
        "https://kaizo.system/kaizo_role": "publisher",
        "https://kaizo.system/tenant_id": "global",
    })
    assert principal.actor_id == "auth0|approved-publisher"
    assert principal.role == "publisher"
    assert principal.tenant_id == "global"
    assert principal.verified is True
    assert principal.source == "oidc_jwt"


def test_namespaced_auth0_academy_claims_resolve_distinct_tenants():
    from productization.identity import _claims_to_principal

    academy_a = _claims_to_principal({
        "sub": "auth0|academy-a-client",
        "https://kaizo.system/kaizo_role": "academy",
        "https://kaizo.system/tenant_id": "academy-a",
    })
    academy_b = _claims_to_principal({
        "sub": "auth0|academy-b-client",
        "https://kaizo.system/kaizo_role": "academy",
        "https://kaizo.system/tenant_id": "academy-b",
    })

    assert academy_a.role == academy_b.role == "academy"
    assert academy_a.tenant_id == "academy-a"
    assert academy_b.tenant_id == "academy-b"
    assert academy_a.tenant_id != academy_b.tenant_id
    assert academy_a.verified is True
    assert academy_b.verified is True
    assert academy_a.source == academy_b.source == "oidc_jwt"


def test_namespaced_auth0_academy_claims_reject_missing_tenant():
    from productization.identity import IdentityNotConfiguredError, _claims_to_principal

    with pytest.raises(IdentityNotConfiguredError, match="missing required KAIZO claims"):
        _claims_to_principal({
            "sub": "auth0|academy-without-tenant",
            "https://kaizo.system/kaizo_role": "academy",
        })
