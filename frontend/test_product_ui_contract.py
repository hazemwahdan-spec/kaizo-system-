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
