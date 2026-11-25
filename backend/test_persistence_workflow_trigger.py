"""Regression guard for exact-head PostgreSQL workflow coverage of Coach lineage."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "persistence-adapter-validation.yml"
STACKED_COACH_BRANCH = "fix/coach-explicit-feat-033-035-parent-lineage-20261124"
STACKED_COACH_BASE_BRANCH = "fix/coach-workflow-parent-toctou-lock-20261123"
STACKED_COACH_UI_BASE_BRANCH = "fix/coach-explicit-feat-033-035-parent-lineage-20261124"


def test_current_stacked_coach_lineage_branch_triggers_postgres_validation():
    source = WORKFLOW.read_text(encoding="utf-8")
    push_block = source.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
    assert f"      - {STACKED_COACH_BRANCH}" in push_block
    pull_request_block = source.split("  pull_request:\n", 1)[1].split("\njobs:", 1)[0]
    assert f"      - {STACKED_COACH_BASE_BRANCH}" in pull_request_block
    assert f"      - {STACKED_COACH_UI_BASE_BRANCH}" in pull_request_block
    assert "productization/test_training_workflow_postgres.py" in source
