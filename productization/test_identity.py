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


def _local_oidc_token(private_key, **overrides):
    import time
    import jwt

    now = int(time.time())
    claims = {
        "sub": "auth0|verified-coach",
        "iss": "https://issuer.example/",
        "aud": "kaizo-api",
        "iat": now,
        "exp": now + 300,
        "https://kaizo.system/kaizo_role": "coach",
        "https://kaizo.system/tenant_id": "TENANT-A",
        "https://kaizo.system/academy_id": "ACADEMY-A",
        "https://kaizo.system/resource_owner_id": "ATHLETE-A",
    }
    claims.update(overrides)
    return jwt.encode(
        claims, private_key, algorithm="RS256", headers={"kid": "local-oidc-test-key"}
    )


def _configure_local_oidc(monkeypatch, public_key):
    from types import SimpleNamespace
    import jwt
    from productization import identity

    issuer = "https://issuer.example/"
    audience = "kaizo-api"
    jwks_url = "https://issuer.example/.well-known/jwks.json"
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_OIDC_ISSUER", issuer)
    monkeypatch.setenv("KAIZO_OIDC_AUDIENCE", audience)
    monkeypatch.setenv("KAIZO_OIDC_JWKS_URL", jwks_url)
    monkeypatch.delenv("KAIZO_OIDC_CLAIM_NAMESPACE", raising=False)

    class LocalJWKClient:
        def __init__(self, url):
            assert url == jwks_url

        def get_signing_key_from_jwt(self, token):
            assert jwt.get_unverified_header(token)["kid"] == "local-oidc-test-key"
            return SimpleNamespace(key=public_key)

    monkeypatch.setattr(identity, "PyJWKClient", LocalJWKClient)


def test_valid_rs256_bearer_derives_verified_coach_and_ignores_forged_headers(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa

    from productization.identity import resolve_principal

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _configure_local_oidc(monkeypatch, private_key.public_key())
    token = _local_oidc_token(private_key)

    principal = resolve_principal(
        actor_id="forged-actor",
        role="administrator",
        tenant_id="FORGED-TENANT",
        resource_owner_id="FORGED-ATHLETE",
        authorization=f"Bearer {token}",
    )

    assert principal.actor_id == "auth0|verified-coach"
    assert principal.role == "coach"
    assert principal.tenant_id == "TENANT-A"
    assert principal.resource_owner_id == "ATHLETE-A"
    assert principal.academy_id == "ACADEMY-A"
    assert principal.verified is True
    assert principal.source == "oidc_jwt"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://wrong-issuer.example/"},
        {"aud": "wrong-api"},
        {"exp": 1},
    ],
)
def test_rs256_bearer_rejects_wrong_issuer_audience_and_expiry(monkeypatch, overrides):
    from cryptography.hazmat.primitives.asymmetric import rsa

    from productization.identity import IdentityNotConfiguredError, resolve_principal

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _configure_local_oidc(monkeypatch, private_key.public_key())
    token = _local_oidc_token(private_key, **overrides)

    with pytest.raises(IdentityNotConfiguredError, match="OIDC token verification failed"):
        resolve_principal("forged", "coach", "TENANT-A", None, f"Bearer {token}")


def test_rs256_bearer_rejects_signature_from_untrusted_key(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa

    from productization.identity import IdentityNotConfiguredError, resolve_principal

    trusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _configure_local_oidc(monkeypatch, trusted_key.public_key())
    token = _local_oidc_token(attacker_key)

    with pytest.raises(IdentityNotConfiguredError, match="OIDC token verification failed"):
        resolve_principal("forged", "coach", "TENANT-A", None, f"Bearer {token}")


@pytest.mark.parametrize(
    "claims",
    [
        {"https://kaizo.system/kaizo_role": "administrator"},
        {"https://kaizo.system/tenant_id": ""},
        {"https://kaizo.system/kaizo_role": ""},
    ],
)
def test_rs256_bearer_requires_valid_role_and_tenant_claims(monkeypatch, claims):
    from cryptography.hazmat.primitives.asymmetric import rsa

    from productization.identity import IdentityNotConfiguredError, resolve_principal

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _configure_local_oidc(monkeypatch, private_key.public_key())
    token = _local_oidc_token(private_key, **claims)

    with pytest.raises(IdentityNotConfiguredError, match="missing required KAIZO claims"):
        resolve_principal("forged", "coach", "TENANT-A", None, f"Bearer {token}")
