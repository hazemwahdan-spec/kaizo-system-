"""Fail-closed containment for audit-trace routes pending Phase 4 controls.

These routes currently lack verified-principal binding and tenant-scoped durable
storage. Return 503 until both controls and their live acceptance tests exist.
This is intentionally a temporary availability trade-off, not authorization.
"""
from fastapi import HTTPException


def require_audit_trace_ready() -> None:
    """Prevent unauthenticated/unscoped trace operations from being accepted."""
    raise HTTPException(
        status_code=503,
        detail=(
            "Audit trace is temporarily disabled pending verified OIDC identity, "
            "role/tenant authorization, and tenant-scoped durable audit storage."
        ),
    )
