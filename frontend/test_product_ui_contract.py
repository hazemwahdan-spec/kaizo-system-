from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "app.js").read_text()
INDEX = (ROOT / "frontend" / "index.html").read_text()

def test_four_commercial_roles_are_present():
    for role in ("academy", "coach", "athlete", "parent"):
        assert f'value="{role}"' in APP

def test_product_api_and_governance_surface_are_present():
    assert 'const PRODUCT_API=API+"/product"' in APP
    assert 'execution_authorized' in APP
    assert 'coach_final_authority' in APP

def test_ui_does_not_authorize_execution():
    assert 'execution_authorized:true' not in APP.replace(" ", "").lower()
    assert 'execution_authorized = true' not in APP.replace(" ", "").lower()

def test_product_title():
    assert "KAIZO SYSTEM" in INDEX


def test_product_api_errors_are_visible_and_safe():
    assert 'Core returned a non-JSON response' in APP
    assert 'response_excerpt:raw.slice(0,500)' in APP
    assert 'escapeHtml(message)' in APP
    assert 'HTTP '+ '"+r.status+' in APP

 
def test_product_requests_require_verified_auth0_bearer():
    assert 'window.KAIZO_AUTH_READY' in APP
    assert '"Authorization":"Bearer "+token' in APP
    assert 'function kaizoLogin()' in APP
    assert 'X-KAIZO headers are not credentials' in APP


def test_coach_roster_uses_verified_owned_athlete_endpoints():
    assert 'productCall("/coach/athletes")' in APP
    assert 'productCall("/coach/athletes/"+encodeURIComponent(athleteId))' in APP
    assert 'productCall("/coach/athletes",{method:"POST"' in APP
    assert 'display_name:name' in APP

def test_coach_roster_does_not_send_client_supplied_identity_scope():
    assert '"X-KAIZO-Actor"' not in APP
    assert '"X-KAIZO-Role"' not in APP
    assert '"X-KAIZO-Tenant"' not in APP
    assert 'opts.headers={...(opts.headers||{}),"Authorization":"Bearer "+token};' in APP

def test_coach_roster_does_not_use_legacy_global_athlete_list():
    assert 'productCall("/athletes")' not in APP
    assert 'productCall("/coach/athletes")' in APP

def test_coach_training_groups_use_verified_scoped_api():
    assert 'productCall("/coach/groups")' in APP
    assert 'productCall("/coach/groups",{method:"POST"' in APP
    assert 'productCall("/coach/groups/"+encodeURIComponent(groupId)+"/athletes"' in APP
    assert 'method:"DELETE"' in APP
    assert 'X-KAIZO-Actor' not in APP


def test_coach_athlete_decision_history_uses_scoped_read_only_api():
    assert 'productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-cycles")' in APP
    assert 'loadCoachAthleteDecisionCycles(athleteId)' in APP
    assert 'No historical records have been generated.' in APP
    assert 'athleteDecisionCycles' in APP


def test_coach_home_dashboard_uses_verified_owned_summary_api():
    assert 'productCall("/coach/dashboard")' in APP
    assert 'loadCoachDashboard()' in APP
    assert 'coachDashboardMetrics' in APP
    assert 'Recent recorded decisions' in APP
    assert 'id="coachPriorityQueue"' in APP
    assert 'no inferred deadlines' in APP


def test_coach_priority_queue_uses_verified_evidence_and_fails_closed():
    assert 'productCall("/coach/priority-queue")' in APP
    assert 'function loadCoachPriorityQueue()' in APP
    assert 'not tracked open tasks' in APP
    assert 'review status not tracked' in APP
    assert 'Coach judgment required' in APP
    assert 'execution_authorized:true' not in APP.replace(" ", "").lower()
    
def test_railway_coach_ui_routes_api_calls_to_core_service():
    auth_config = (ROOT / "frontend" / "auth-config.js").read_text()
    assert 'window.location.hostname === "kaizo-coach-production.up.railway.app"' in auth_config
    assert '"https://kaizo-core-engine-production.up.railway.app/api/v1"' in auth_config
    assert ': "/api/v1"' in auth_config

def test_coach_ui_fails_closed_for_unscoped_core_decision_and_digital_twin_actions():
    for route in (
        "/rules/evaluate",
        "/decision/adapt",
        "/decision/loop",
        "/digital-twin/sync",
        "/digital-twin/",
        "/audit/logs",
    ):
        assert route not in APP
    assert "Protected Coach workflow boundary" in APP
    assert "Legacy unscoped Core routes remain retired" in APP
    assert "no unscoped request will be sent" in APP
    assert 'id="coachWorkspace"' not in APP
    assert "coachGo(" not in APP


def test_coach_audit_review_uses_selected_owned_athlete_and_product_bearer():
    assert '"/coach/athletes/"+encodeURIComponent(athleteId)+"/audit-review?query="+encodeURIComponent(query)' in APP
    assert "function loadCoachAthleteAuditReview()" in APP
    assert "athleteAuditReviewSection" in APP
    assert "productAccessToken()" in APP
    assert 'fetch(API+"/audit/logs"' not in APP


def test_coach_ui_decision_cycle_and_adaptation_use_protected_scoped_api():
    assert 'productCall("/decision",{method:"POST"' in APP
    assert 'productCall("/adaptation",{method:"POST"' in APP
    assert 'decision_cycle_id:currentCoachDecisionCycleId' in APP
    assert '"/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-cycles/"+encodeURIComponent(cycleId)' in APP
    assert 'function createCoachDecisionCycle(event)' in APP
    assert 'function adaptCoachDecisionCycle(event)' in APP
    assert "execution_authorized:true" not in APP.replace(" ", "").lower()
