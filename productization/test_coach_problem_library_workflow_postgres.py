from __future__ import annotations

import uuid
import pytest

import persistence
from productization import coach_assessment_workflow, coach_problem_library_workflow, coach_roster


pytestmark = pytest.mark.skipif(
    not persistence.is_postgres_enabled(),
    reason="requires disposable PostgreSQL service",
)


def _item(item_id, **overrides):
    item = {
        "knowledge_id": item_id, "id": item_id, "domain": "problem",
        "title": "Entry timing problem", "source_type": "problem_library",
        "source_ref": "problem-library://entry-timing/" + item_id, "source_version": "1.0",
        "provenance_note": "Approved canonical problem entry with source traceability.",
        "evidence_refs": ["evidence://problem-library/" + item_id],
        "evidence_status": "VERIFIED", "lifecycle_status": "APPROVED",
        "changed_by": "knowledge-curator", "updated_at": "2026-11-10T00:00:00Z",
    }
    item.update(overrides)
    persistence.upsert_knowledge(item_id, item, item["updated_at"])
    return item


def _scope():
    persistence.initialize()
    tenant = "TENANT-" + uuid.uuid4().hex
    coach = "auth0|coach-" + uuid.uuid4().hex
    other_coach = "auth0|coach-" + uuid.uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="Library Athlete")
    other_athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=other_coach, display_name="Other Library Athlete")
    assessment = coach_assessment_workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        template_id="LIBRARY-BASELINE", measurements={"entry_quality": 7})
    other_assessment = coach_assessment_workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=other_coach, athlete_id=other_athlete["athlete_id"],
        template_id="LIBRARY-BASELINE-OTHER", measurements={"entry_quality": 6})
    return tenant, coach, other_coach, athlete["athlete_id"], assessment["assessment_id"], other_athlete["athlete_id"], other_assessment["assessment_id"]


def test_postgres_problem_library_selection_requires_provenance_and_ownership():
    tenant, coach, other_coach, athlete_id, assessment_id, other_athlete_id, other_assessment_id = _scope()
    approved_id = "PRB-017-" + uuid.uuid4().hex
    draft_id = "PRB-017-" + uuid.uuid4().hex
    legacy_id = "PRB-017-" + uuid.uuid4().hex
    _item(approved_id)
    _item(draft_id, lifecycle_status="DRAFT")
    persistence.upsert_knowledge(legacy_id, {
        "id": legacy_id, "domain": "problem", "status": "Published",
        "title": "Legacy item without provenance",
    }, "2026-11-10T00:00:00Z")
    items = coach_problem_library_workflow.list_approved_problem_library()
    assert approved_id in {x["knowledge_id"] for x in items}
    assert draft_id not in {x["knowledge_id"] for x in items}
    assert legacy_id not in {x["knowledge_id"] for x in items}

    selection = coach_problem_library_workflow.select_problem_library_item(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment_id, library_item_id=approved_id)
    assert selection["selected_by"] == coach
    assert selection["execution_authorized"] is False
    assert coach_problem_library_workflow.get_problem_library_selection(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment_id, selection_id=selection["selection_id"])["selection_id"] == selection["selection_id"]
    assert coach_problem_library_workflow.list_problem_library_selections(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment_id)[0]["selection_id"] == selection["selection_id"]
    assert coach_problem_library_workflow.list_problem_library_selections(
        tenant_id=tenant, coach_actor_id=other_coach, athlete_id=athlete_id,
        assessment_id=assessment_id) is None
    assert coach_problem_library_workflow.select_problem_library_item(
        tenant_id=tenant, coach_actor_id=other_coach, athlete_id=athlete_id,
        assessment_id=assessment_id, library_item_id=approved_id) is None
    with pytest.raises(coach_problem_library_workflow.CoachProblemLibraryConflict):
        coach_problem_library_workflow.select_problem_library_item(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            assessment_id=assessment_id, library_item_id=legacy_id)


def test_postgres_problem_library_selection_audit_failure_rolls_back(monkeypatch):
    tenant, coach, other_coach, athlete_id, assessment_id, other_athlete_id, other_assessment_id = _scope()
    item_id = "PRB-017-" + uuid.uuid4().hex
    _item(item_id)

    def fail_audit(**kwargs):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        coach_problem_library_workflow.select_problem_library_item(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            assessment_id=assessment_id, library_item_id=item_id)
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM kaizo_problem_library_selections WHERE athlete_id=%s AND assessment_id=%s",
                (athlete_id, assessment_id))
            assert cur.fetchone()[0] == 0


def test_postgres_problem_library_rejects_assessment_from_another_athlete():
    tenant, coach, other_coach, athlete_id, assessment_id, other_athlete_id, other_assessment_id = _scope()
    item_id = "PRB-017-" + uuid.uuid4().hex
    _item(item_id)
    assert coach_problem_library_workflow.select_problem_library_item(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=other_assessment_id, library_item_id=item_id) is None
