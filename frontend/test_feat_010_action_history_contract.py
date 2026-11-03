from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "app.js").read_text()
CONTRACT = (ROOT / "docs" / "product" / "FEAT-010-ACCEPTANCE-CRITERIA.md").read_text()


def test_feat_010_uses_only_verified_coach_scoped_action_history_endpoint():
    assert 'productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/action-history")' in APP
    assert "function loadCoachActionHistory(athleteId)" in APP
    assert 'productCall("/api/v1/audit' not in APP
    assert "athleteActionHistorySection" in APP


def test_feat_010_distinguishes_verified_audit_actor_from_unverified_feat044_link():
    assert "actor_attribution_verified" in APP
    assert "Related state link — actor attribution not verified" in APP
    assert 'escapeHtml(item.actor_id||"")' in APP
    assert "escapeHtml(item.reason||" in APP
    assert "escapeHtml(detail)" in APP


def test_feat_010_history_is_read_only_and_fails_closed():
    start = APP.index("async function loadCoachActionHistory(athleteId)")
    end = APP.index("async function loadCoachAthleteStatusHistory", start)
    helper = APP[start:end]
    assert "method:" not in helper
    assert "INSUFFICIENT_EVIDENCE" in helper
    assert "NO_RECORDED_ACTIONS" in helper
    assert "No action data is displayed when authentication or authorization fails." in helper
    assert "tenant-scoped events attributable to this verified Coach" in APP
    assert "read-only" in CONTRACT
    assert "Unscoped legacy audit rows" in CONTRACT
    assert "FEAT-044" in CONTRACT
    assert "execution_authorized=false" in CONTRACT
