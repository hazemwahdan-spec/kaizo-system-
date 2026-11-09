"""Fail-closed gate for Coach knowledge routes pending verified scope."""
from fastapi import HTTPException


def require_knowledge_runtime_ready() -> None:
    """Disable unscoped knowledge reads/writes until the security contract exists."""
    raise HTTPException(
        status_code=503,
        detail=(
            "Knowledge runtime is temporarily disabled pending verified OIDC Coach "
            "identity, role/tenant authorization, tenant-scoped storage, and atomic audit."
        ),
    )
