"""Phase 7 identity boundary.

Development header identity is explicitly non-production. Production mode fails closed
until a real authentication/identity provider is connected and verified.
"""
import os
from dataclasses import dataclass


class IdentityNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    actor_id: str
    role: str
    tenant_id: str
    resource_owner_id: str | None
    verified: bool
    source: str


VALID_ROLES = {"academy", "coach", "athlete", "parent"}


def resolve_principal(
    actor_id: str,
    role: str,
    tenant_id: str,
    resource_owner_id: str | None,
) -> Principal:
    mode = os.getenv("KAIZO_IDENTITY_MODE", "production").strip().lower()

    if mode == "development":
        if not actor_id or not tenant_id or role not in VALID_ROLES:
            raise IdentityNotConfiguredError("development identity headers are incomplete")
        return Principal(
            actor_id=actor_id,
            role=role,
            tenant_id=tenant_id,
            resource_owner_id=resource_owner_id,
            verified=False,
            source="development_headers",
        )

    if mode in {"oidc", "oauth2", "external"}:
        raise IdentityNotConfiguredError(
            "external identity provider is not connected and production identity is not verified"
        )

    raise IdentityNotConfiguredError(
        "production identity is fail-closed until a real authentication provider is connected"
    )
