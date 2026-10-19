"""Phase 4 regression tests for durable tenant-scoped audit storage.

These tests exercise the persistence primitive only. They do not enable any
public audit endpoint or claim that identity/role authorization is complete.
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/kaizo_test"

import persistence


def test_tenant_scoped_audit_reads_isolate_tenants_and_exclude_legacy_rows():
    persistence.initialize()
    suffix = uuid.uuid4().hex
    tenant_a = f"tenant-a-{suffix}"
    tenant_b = f"tenant-b-{suffix}"
    action_a = f"TENANT_A_EVENT_{suffix}"
    action_b = f"TENANT_B_EVENT_{suffix}"
    legacy_action = f"UNSCOPED_LEGACY_EVENT_{suffix}"

    persistence.append_tenant_audit(
        tenant_id=tenant_a, timestamp="2026-10-19T00:00:00Z",
        who="test-actor-a", action=action_a, old_value=None,
        new_value={"tenant": "a"}, why="tenant isolation regression",
    )
    persistence.append_tenant_audit(
        tenant_id=tenant_b, timestamp="2026-10-19T00:00:01Z",
        who="test-actor-b", action=action_b, old_value=None,
        new_value={"tenant": "b"}, why="tenant isolation regression",
    )
    # Existing call sites still create unscoped records until trusted-principal
    # propagation is implemented. They must never appear in scoped reads.
    persistence.append_audit(
        timestamp="2026-10-19T00:00:02Z", who="legacy-actor",
        action=legacy_action, old_value=None, new_value={"legacy": True},
        why="legacy rows remain unscoped",
    )

    rows_a = persistence.list_tenant_audit_logs(tenant_id=tenant_a)
    rows_b = persistence.list_tenant_audit_logs(tenant_id=tenant_b)
    assert [row["action"] for row in rows_a] == [action_a]
    assert [row["action"] for row in rows_b] == [action_b]
    assert all(row["tenant_id"] == tenant_a for row in rows_a)
    assert all(row["tenant_id"] == tenant_b for row in rows_b)
    assert legacy_action not in {row["action"] for row in rows_a + rows_b}


@pytest.mark.parametrize("tenant_id", ["", " ", None])
def test_tenant_scoped_audit_rejects_missing_tenant(tenant_id):
    with pytest.raises(ValueError, match="tenant_id is required"):
        persistence.list_tenant_audit_logs(tenant_id=tenant_id)
    with pytest.raises(ValueError, match="tenant_id is required"):
        persistence.append_tenant_audit(
            tenant_id=tenant_id, timestamp="2026-10-19T00:00:00Z",
            who="actor", action="INVALID_SCOPE", old_value=None,
            new_value=None, why="missing tenant must fail closed",
        )
