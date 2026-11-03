import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "productization" / "product-surface-contract.json"


def test_product_surface_contract_is_governed():
    data = json.loads(CONTRACT.read_text())
    assert data["phase"] == 7
    assert data["execution_authorized_default"] is False
    assert data["coach_final_authority"] is True
    assert data["evidence_before_claim"] is True
    assert set(data["roles"]) == {"academy", "coach", "athlete", "parent"}
    assert "execution_authorized=true" in data["global_denials"]


def test_read_only_roles_have_no_writes():
    data = json.loads(CONTRACT.read_text())
    assert data["roles"]["athlete"]["writes"] is False
    assert data["roles"]["parent"]["writes"] is False


def test_product_surface_never_claims_production_verification():
    data = json.loads(CONTRACT.read_text())
    assert data["production_verified"] is False


def test_feat_007_queue_is_a_verified_coach_read_surface():
    data = json.loads(CONTRACT.read_text())
    coach = data["roles"]["coach"]
    assert "coach_current_priority_queue" in coach["surfaces"]
    assert "view_evidence_backed_current_priority_queue" in coach["allowed_actions"]
    assert "verified_coach_tenant_scope_for_priority_queue_reads" in coach["mutation_requires"]
    assert data["coach_final_authority"] is True
    assert data["execution_authorized_default"] is False
