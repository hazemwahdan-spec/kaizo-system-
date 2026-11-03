from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "app.js").read_text()
CONTRACT = (ROOT / "docs" / "product" / "FEAT-008-ACCEPTANCE-CRITERIA.md").read_text()


def test_feat_008_search_is_limited_to_loaded_verified_coach_roster():
    assert 'productCall("/coach/athletes")' in APP
    assert 'let coachRosterRecords=[]' in APP
    assert 'function filterCoachRoster()' in APP
    assert 'display_name||"").toLocaleLowerCase().includes(term)' in APP
    assert 'athlete_id||"").toLocaleLowerCase().includes(term)' in APP
    assert 'No athletes in your roster match this search.' in APP
    assert 'productCall("/athletes")' not in APP


def test_feat_008_navigates_existing_scoped_athlete_workflow_sections():
    for section in ("athleteProfileSection", "athleteLifecycleSection",
                    "athleteStatusHistorySection", "athleteDecisionCyclesSection"):
        assert section in APP
    assert 'function coachAthleteSection(sectionId)' in APP
    assert 'function returnCoachRoster()' in APP
    assert 'onclick="returnCoachRoster()"' in APP
    assert 'productCall("/coach/athletes/"+encodeURIComponent(athleteId))' in APP
    assert '"/status-history"' in APP
    assert '"/decision-cycles"' in APP


def test_feat_008_escapes_untrusted_athlete_data_and_fails_closed():
    assert "escapeHtml(athlete?.display_name||result.display_name||athleteId)" in APP
    assert "escapeHtml(pretty(result))" in APP
    assert "escapeHtml(a.display_name||a.athlete_id)" in APP
    assert "No roster data is displayed when authentication or authorization fails." in APP
    assert 'Coach Final Authority' in APP
    assert "execution_authorized" in APP\n    assert "execution_authorized:true" not in APP.replace(" ", "").lower()


def test_feat_008_acceptance_contract_preserves_scope_and_governance():
    assert "verified Coach roster" in CONTRACT
    assert "No client-supplied Coach/tenant identity headers" in CONTRACT
    assert "read-only" in CONTRACT
    assert "execution_authorized=false" in CONTRACT
    assert "No new data model" in CONTRACT
