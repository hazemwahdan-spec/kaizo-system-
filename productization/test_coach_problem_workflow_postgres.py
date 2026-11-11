from __future__ import annotations

import uuid
import pytest

import persistence
from productization import coach_assessment_workflow, coach_problem_workflow, coach_roster


pytestmark = pytest.mark.skipif(
    not persistence.is_postgres_enabled(),
    reason="requires disposable PostgreSQL service",
)


def _scope():
    persistence.initialize()
    tenant = "TENANT-" + uuid.uuid4().hex
    coach = "auth0|coach-" + uuid.uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="Problem Workflow Athlete")
    assessment = coach_assessment_workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        template_id="PROBLEM-BASELINE", measurements={"entry_quality": 7})
    return tenant, coach, athlete["athlete_id"], assessment["assessment_id"]


def test_postgres_problem_statement_persists_and_is_coach_scoped():
    tenant, coach, athlete_id, assessment_id = _scope()
    record = coach_problem_workflow.create_problem_statement(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment_id, statement="Late entry under pressure",
        problem_type="technical_execution", context={"phase": "tsukuri"},
        structured_fields={"observable": "late_entry"})
    assert record is not None
    assert coach_problem_workflow.get_problem_statement(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        problem_id=record["problem_id"]) == record
    assert coach_problem_workflow.get_problem_statement(
        tenant_id=tenant, coach_actor_id="auth0|other",
        athlete_id=athlete_id, problem_id=record["problem_id"]) is None
    assert coach_problem_workflow.list_problem_statements(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id) == [record]
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s AND action='COACH_PROBLEM_STATEMENT_CREATED'""",
                (tenant, coach))
            assert cur.fetchone()[0] == 1


def test_postgres_problem_statement_audit_failure_rolls_back(monkeypatch):
    tenant, coach, athlete_id, assessment_id = _scope()

    def fail_audit(**kwargs):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        coach_problem_workflow.create_problem_statement(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            assessment_id=assessment_id, statement="Must roll back",
            problem_type="technical_execution")
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_problem_statements
                   WHERE athlete_id=%s AND statement='Must roll back'""",
                (athlete_id,))
            assert cur.fetchone()[0] == 0


def test_postgres_lost_ownership_prevents_problem_statement_write():
    tenant, coach, athlete_id, assessment_id = _scope()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s""",
                (tenant, coach, athlete_id))
        conn.commit()
    assert coach_problem_workflow.create_problem_statement(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment_id, statement="Ownership revoked",
        problem_type="technical_execution") is None
