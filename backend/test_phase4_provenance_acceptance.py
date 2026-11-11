"""Phase 4 knowledge provenance is fail-closed until verified Coach scope exists."""
import os
import uuid

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/kaizo_test"

from fastapi.testclient import TestClient
from main import app
import knowledge_runtime
import persistence

persistence.initialize()
client = TestClient(app)
BASE = "/api/v1/knowledge-runtime"


def provenance(**overrides):
    suffix = uuid.uuid4().hex[:8]
    body = {
        "knowledge_id": f"P4-KNOWLEDGE-{suffix}",
        "source_type": "IJF",
        "source_ref": "P4-SOURCE-001",
        "source_version": "2026.1",
        "evidence_status": "VERIFIED",
        "provenance_note": "Versioned source with explicit evidence status",
        "evidence_refs": ["P4-EVIDENCE-001"],
        "changed_by": "forged-coach",
        "coach_final_authority": True,
    }
    body.update(overrides)
    return body


def test_phase4_047_050_routes_fail_closed_without_any_persistence_side_effect():
    knowledge_runtime.MEMORY_ITEMS.clear()
    knowledge_runtime.MEMORY_LINKS.clear()
    body = provenance()
    cases = [
        (f"{BASE}/feat-047/provenance", body),
        (f"{BASE}/feat-048/lifecycle", {
            "knowledge_id": body["knowledge_id"], "lifecycle_status": "APPROVED",
            "changed_by": "forged-coach", "coach_final_authority": True,
        }),
        (f"{BASE}/feat-049/retrieve", {
            "workflow_context": "Phase 4 decision", "query": body["knowledge_id"],
            "requested_by": "forged-coach", "coach_final_authority": True,
        }),
        (f"{BASE}/feat-050/link", {
            "knowledge_id": body["knowledge_id"], "unit_id": "UNIT-1",
            "link_type": "SUPPORTS", "evidence_refs": ["P4-EVIDENCE-001"],
            "linked_by": "forged-coach", "coach_final_authority": True,
        }),
    ]
    for path, request_body in cases:
        response = client.post(path, json=request_body)
        assert response.status_code == 503, (path, response.status_code, response.text)
        assert "temporarily disabled" in response.text

    assert knowledge_runtime.MEMORY_ITEMS == {}
    assert knowledge_runtime.MEMORY_LINKS == []
    assert persistence.load_knowledge().get(body["knowledge_id"]) is None


def test_phase4_047_050_remain_closed_for_invalid_status_or_forged_bearer():
    body = provenance(evidence_status="TRUST_ME")
    response = client.post(f"{BASE}/feat-047/provenance", json=body)
    assert response.status_code == 503, response.text

    response = client.post(
        f"{BASE}/feat-047/provenance",
        json=provenance(),
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 503, response.text

    assert knowledge_runtime.MEMORY_ITEMS == {}
    assert knowledge_runtime.MEMORY_LINKS == []


if __name__ == "__main__":
    test_phase4_047_050_routes_fail_closed_without_any_persistence_side_effect()
    test_phase4_047_050_remain_closed_for_invalid_status_or_forged_bearer()
    print("Phase 4 knowledge runtime fail-closed acceptance passed")
