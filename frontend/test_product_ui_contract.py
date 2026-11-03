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



def test_coach_action_history_is_connected_through_verified_product_api():
    assert 'id="coach-action-history"' in APP
    assert 'function loadCoachActions()' in APP
    assert 'productCall("/coach/actions?limit=50")' in APP
    assert 'verified, tenant-scoped API' in APP
