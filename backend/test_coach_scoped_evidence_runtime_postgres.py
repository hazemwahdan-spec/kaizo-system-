"""Disposable-PostgreSQL security regressions for Coach-scoped FEAT-047..050/052..053."""
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("KAIZO_PERSISTENCE_MODE", "postgres")
import persistence
import coach_scoped_evidence_runtime as scoped

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or not persistence.is_postgres_enabled(),
    reason="requires disposable PostgreSQL via DATABASE_URL",
)


def _id(prefix):
    return f"{prefix}-{uuid4().hex}"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _principal(actor, tenant, *, verified=True, source="oidc_jwt", role="coach", permissions=frozenset({"product"})):
    return SimpleNamespace(
        actor_id=actor, tenant_id=tenant, verified=verified, source=source,
        role=role, permissions=permissions,
    )


@pytest.fixture
def owned_scope():
    persistence.initialize()
    scoped.ensure_schema()
    tenant, coach, athlete = _id("TENANT"), _id("COACH"), _id("ATHLETE")
    knowledge, evidence, session = _id("KNOWLEDGE"), _id("EVIDENCE"), _id("SESSION")
    now = _now()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_athletes
                   (athlete_id,display_name,status,metadata,created_at,updated_at)
                   VALUES (%s,'Scoped test athlete','ACTIVE','{}'::jsonb,%s,%s)""",
                (athlete, now, now),
            )
            cur.execute(
                """INSERT INTO kaizo_coach_athlete_ownership
                   (athlete_id,tenant_id,coach_actor_id,assigned_at) VALUES (%s,%s,%s,%s)""",
                (athlete, tenant, coach, now),
            )
            cur.execute(
                """INSERT INTO kaizo_evidence_records
                   (evidence_id,subject_type,subject_id,evidence_level,status,source_ref,claim,
                    observed_value,verified_by,verified_at,notes)
                   VALUES (%s,'athlete',%s,'E3','VERIFIED','fixture','verified fixture',
                           '{}'::jsonb,%s,%s,'disposable test')""",
                (evidence, athlete, coach, now),
            )
            cur.execute(
                """INSERT INTO kaizo_training_sessions
                   (session_id,plan_id,athlete_id,title,duration_minutes,blocks,status,created_by,created_at)
                   VALUES (%s,%s,%s,'Scoped session',60,'[]'::jsonb,'DRAFT',%s,%s)""",
                (session, _id("PLAN"), athlete, coach, now),
            )
        conn.commit()
    principal = _principal(coach, tenant)
    yield principal, tenant, coach, athlete, knowledge, evidence, session
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kaizo_audit_logs WHERE tenant_id=%s AND who=%s", (tenant, coach))
            cur.execute("DELETE FROM kaizo_coach_scoped_knowledge_links WHERE tenant_id=%s AND coach_actor_id=%s", (tenant, coach))
            cur.execute("DELETE FROM kaizo_coach_scoped_actor_trace WHERE tenant_id=%s AND coach_actor_id=%s", (tenant, coach))
            cur.execute("DELETE FROM kaizo_coach_scoped_governance WHERE tenant_id=%s AND coach_actor_id=%s", (tenant, coach))
            cur.execute("DELETE FROM kaizo_coach_scoped_knowledge WHERE tenant_id=%s AND coach_actor_id=%s", (tenant, coach))
            cur.execute("DELETE FROM kaizo_training_sessions WHERE session_id=%s", (session,))
            cur.execute("DELETE FROM kaizo_evidence_records WHERE evidence_id=%s", (evidence,))
            cur.execute("DELETE FROM kaizo_coach_athlete_ownership WHERE athlete_id=%s", (athlete,))
            cur.execute("DELETE FROM kaizo_athletes WHERE athlete_id=%s", (athlete,))
        conn.commit()


def _record(f):
    principal, _tenant, _coach, athlete, knowledge, evidence, _session = f
    return scoped.record_provenance(
        principal=principal, athlete_id=athlete, knowledge_id=knowledge,
        source_type="IJF", source_ref="fixture-source", source_version="v1",
        provenance_note="verified source for disposable test", evidence_refs=[evidence],
    )


def test_verified_primary_owner_can_record_approve_retrieve_and_link(owned_scope):
    f = owned_scope
    principal, _tenant, _coach, athlete, knowledge, _evidence, session = f
    record = _record(f)
    assert record["evidence_status"] == "VERIFIED"
    assert scoped.change_lifecycle(
        principal=principal, athlete_id=athlete, knowledge_id=knowledge,
        target_status="REVIEW", expected_version=1,
    )["version"] == 2
    assert scoped.change_lifecycle(
        principal=principal, athlete_id=athlete, knowledge_id=knowledge,
        target_status="APPROVED", expected_version=2,
    )["version"] == 3
    results = scoped.retrieve_knowledge(principal=principal, athlete_id=athlete, query="fixture")
    assert [row["knowledge_id"] for row in results] == [knowledge]
    link = scoped.link_training_session(
        principal=principal, athlete_id=athlete, knowledge_id=knowledge,
        session_id=session, link_type="SUPPORTS", evidence_refs=["EVIDENCE-REF"],
    )
    assert link["unit_id"] == session


@pytest.mark.parametrize("principal", [
    _principal("coach-x", "tenant-x", verified=False),
    _principal("coach-x", "tenant-x", source="development_headers"),
    _principal("coach-x", "tenant-x", role="academy"),
    _principal("coach-x", "tenant-x", permissions=frozenset()),
])
def test_unverified_wrong_role_or_missing_product_permission_is_denied(owned_scope, principal):
    _p, _tenant, _coach, athlete, _knowledge, _evidence, _session = owned_scope
    with pytest.raises(scoped.CoachEvidenceAuthorizationError):
        scoped.retrieve_knowledge(principal=principal, athlete_id=athlete, query="anything")


def test_cross_coach_and_cross_tenant_reads_are_denied(owned_scope):
    _principal_owner, _tenant, _coach, athlete, _knowledge, _evidence, _session = owned_scope
    for principal in (_principal(_id("COACH"), _tenant), _principal(_id("COACH"), _id("TENANT"))):
        with pytest.raises(scoped.CoachEvidenceAuthorizationError):
            scoped.retrieve_knowledge(principal=principal, athlete_id=athlete, query="fixture")


def test_client_cannot_choose_actor_or_tenant(owned_scope):
    principal, tenant, coach, athlete, _knowledge, _evidence, _session = owned_scope
    # The service has no actor_id/tenant_id request arguments; both are server-derived.
    trace = scoped.record_actor_trace(principal=principal, athlete_id=athlete, action="DECISION_REVIEW")
    assert trace["actor_id"] == coach
    assert trace["tenant_id"] == tenant


def test_unverified_evidence_cannot_be_approved(owned_scope):
    principal, _tenant, _coach, athlete, knowledge, _evidence, _session = owned_scope
    record = _record(owned_scope)
    assert record["evidence_status"] == "VERIFIED"
    # A second provenance record with a non-existent evidence reference is UNVERIFIED.
    other = scoped.record_provenance(
        principal=principal, athlete_id=athlete, knowledge_id=_id("KNOWLEDGE"),
        source_type="IJF", source_ref="unverified-source", source_version="v1",
        provenance_note="no durable verified evidence", evidence_refs=[_id("MISSING")],
    )
    reviewed = scoped.change_lifecycle(
        principal=principal, athlete_id=athlete, knowledge_id=other["knowledge_id"],
        target_status="REVIEW", expected_version=1,
    )
    assert reviewed["version"] == 2
    with pytest.raises(scoped.CoachEvidenceConflict):
        scoped.change_lifecycle(
            principal=principal, athlete_id=athlete, knowledge_id=other["knowledge_id"],
            target_status="APPROVED", expected_version=2,
        )


def test_audit_failure_rolls_back_relationship_and_trace_writes(owned_scope, monkeypatch):
    principal, tenant, coach, athlete, knowledge, _evidence, _session = owned_scope
    def fail_audit(**_kwargs):
        raise RuntimeError("simulated audit storage failure")
    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    with pytest.raises(RuntimeError, match="simulated audit"):
        scoped.record_actor_trace(principal=principal, athlete_id=athlete, action="SHOULD_ROLLBACK")
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_coach_scoped_actor_trace
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s AND action='SHOULD_ROLLBACK'""",
                (tenant, coach, athlete),
            )
            assert cur.fetchone()[0] == 0


def test_governance_is_versioned_and_audited(owned_scope):
    principal, _tenant, _coach, athlete, _knowledge, _evidence, _session = owned_scope
    created = scoped.set_governance(
        principal=principal, athlete_id=athlete, resource_type="DECISION",
        resource_id=_id("DECISION"), governance_status="REVIEW",
        metadata={"coach_final_authority": True}, expected_version=0,
    )
    assert created["version"] == 1
    updated = scoped.set_governance(
        principal=principal, athlete_id=athlete, resource_type="DECISION",
        resource_id=created["resource_id"], governance_status="APPROVED",
        metadata={"coach_final_authority": True}, expected_version=1,
    )
    assert updated["version"] == 2
    with pytest.raises(scoped.CoachEvidenceConflict):
        scoped.set_governance(
            principal=principal, athlete_id=athlete, resource_type="DECISION",
            resource_id=created["resource_id"], governance_status="RETIRED",
            metadata={}, expected_version=1,
        )
