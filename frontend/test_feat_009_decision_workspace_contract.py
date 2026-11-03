from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "app.js").read_text()
CONTRACT = (ROOT / "docs" / "product" / "FEAT-009-ACCEPTANCE-CRITERIA.md").read_text()


def test_feat_009_workspace_uses_only_verified_coach_scoped_read_endpoint():
    assert 'productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-workspace")' in APP
    assert 'productCall("/api/v1/assessments/' not in APP
    assert '"/api/v1/assessments/"' not in APP
    assert "function loadCoachDecisionWorkspace(athleteId)" in APP
    assert "if(selectedCoachAthleteId!==String(athleteId))return;" in APP


def test_feat_009_workspace_renders_existing_cycle_evidence_and_lineage():
    for field in ("assessments", "state_snapshots", "problem_statements",
                  "cause_context_framings", "diagnoses", "decision_candidates",
                  "decision_rationales", "decision_comparisons", "coach_reviews",
                  "decisions", "training_plans", "training_sessions", "training_records"):
        assert f"data.{field}" in APP
    assert "Assessments and attached evidence" in APP
    assert "Evidence-linked diagnoses" in APP
    assert "Training / response / retest records" in APP
    assert "escapeHtml(pretty(record))" in APP


def test_feat_009_workspace_fails_closed_and_is_read_only():
    assert 'data.status==="INSUFFICIENT_EVIDENCE"' in APP
    assert 'data.status==="NO_RECORDED_CYCLE"' in APP
    assert "No workspace data is displayed when authentication or authorization fails." in APP
    assert "GET /coach/athletes" in CONTRACT
    assert "read-only" in CONTRACT
    assert "audit event" in CONTRACT
    assert "execution_authorized=false" in CONTRACT
