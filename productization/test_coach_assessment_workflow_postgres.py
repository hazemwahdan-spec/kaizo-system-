from __future__ import annotations

import uuid

import pytest

import persistence
from productization import coach_assessment_workflow as workflow
from productization import coach_roster


pytestmark = pytest.mark.skipif(
    not persistence.is_postgres_enabled(),
    reason="requires disposable PostgreSQL service",
)


def _scope():
    persistence.initialize()
    tenant = "TENANT-" + uuid.uuid4().hex
    coach = "auth0|coach-" + uuid.uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="PostgreSQL Coach Athlete"
    )
    return tenant, coach, athlete["athlete_id"]


def test_postgres_assessment_kpi_capture_and_snapshot_are_durable_and_scoped():
    tenant, coach, athlete_id = _scope()
    assessment = workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        template_id="POSTGRES-U15", measurements={"entry_quality": 8},
    )
    assert assessment is not None
    assert workflow.get_assessment(
        tenant_id=tenant, coach_actor_id=coach,
        athlete_id=athlete_id, assessment_id=assessment["assessment_id"],
    ) == assessment
    assert workflow.get_assessment(
        tenant_id=tenant, coach_actor_id="auth0|other-coach",
        athlete_id=athlete_id, assessment_id=assessment["assessment_id"],
    ) is None

    definition = workflow.create_kpi_definition(
        tenant_id=tenant, coach_actor_id=coach, kpi_id="GRIP-" + uuid.uuid4().hex,
        name="Grip strength", metric_name="grip_strength", unit="kg",
        target=25.0, direction="higher_is_better",
    )
    capture = workflow.create_kpi_capture(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        kpi_id=definition["kpi_id"], value=19.25,
        assessment_id=assessment["assessment_id"],
    )
    assert capture is not None
    assert workflow.get_kpi_capture(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        capture_id=capture["capture_id"],
    ) == capture

    snapshot = workflow.create_state_snapshot(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment["assessment_id"], snapshot_type="baseline",
        kpi_capture_ids=[capture["capture_id"]],
    )
    assert snapshot is not None
    readback = workflow.get_state_snapshot(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        snapshot_id=snapshot["snapshot_id"],
    )
    assert readback == snapshot
    assert workflow.get_state_snapshot(
        tenant_id=tenant, coach_actor_id="auth0|other-coach",
        athlete_id=athlete_id, snapshot_id=snapshot["snapshot_id"],
    ) is None

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s
                     AND action IN ('COACH_ASSESSMENT_RECORDED',
                                    'COACH_KPI_DEFINED',
                                    'COACH_KPI_CAPTURED',
                                    'COACH_STATE_SNAPSHOT_CREATED')""",
                (tenant, coach),
            )
            assert cur.fetchone()[0] == 4


def test_postgres_evidence_attachment_requires_assessment_subject_and_is_atomic():
    tenant, coach, athlete_id = _scope()
    assessment = workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        template_id="POSTGRES-EVIDENCE", measurements={"score": 7},
    )
    evidence_id = "EVID-" + uuid.uuid4().hex
    now = workflow._now()
    persistence.upsert_evidence({
        "evidence_id": evidence_id, "subject_type": "assessment",
        "subject_id": assessment["assessment_id"], "evidence_level": "E2",
        "status": "VERIFIED", "source_ref": "TEST-REF",
        "claim": "Assessment evidence fixture", "observed_value": {"score": 7},
        "verified_by": coach, "verified_at": now, "notes": "Disposable test fixture",
    })
    attached = workflow.attach_assessment_evidence(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment["assessment_id"], evidence_id=evidence_id,
    )
    assert attached is not None
    assert workflow.list_assessment_evidence(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment["assessment_id"],
    ) == [attached]
    with pytest.raises(workflow.CoachWorkflowNotFound):
        workflow.attach_assessment_evidence(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            assessment_id=assessment["assessment_id"], evidence_id="missing-evidence",
        )


def test_postgres_lost_ownership_prevents_assessment_write():
    tenant, coach, athlete_id = _scope()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s""",
                (tenant, coach, athlete_id),
            )
        conn.commit()

    result = workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        template_id="SHOULD-NOT-WRITE", measurements={"score": 1},
    )
    assert result is None
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM kaizo_assessments WHERE athlete_id=%s",
                (athlete_id,),
            )
            assert cur.fetchone()[0] == 0


def test_postgres_domain_write_rolls_back_when_tenant_audit_fails(monkeypatch):
    tenant, coach, athlete_id = _scope()

    def fail_audit(**kwargs):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        workflow.create_assessment(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            template_id="ROLLBACK-TEST", measurements={"score": 9},
        )

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_assessments
                   WHERE athlete_id=%s AND template_id='ROLLBACK-TEST'""",
                (athlete_id,),
            )
            assert cur.fetchone()[0] == 0
