import os
os.environ["KAIZO_PERSISTENCE_MODE"] = "memory"

from fastapi.testclient import TestClient
from main import app
import knowledge_runtime

client = TestClient(app)


def test_047_050_routes_fail_closed_before_any_read_or_write():
    knowledge_runtime.MEMORY_ITEMS.clear()
    knowledge_runtime.MEMORY_LINKS.clear()
    cases = [
        ("/api/v1/knowledge-runtime/feat-047/provenance", {
            "knowledge_id": "K-1", "source_type": "IJF", "source_ref": "REF-047",
            "source_version": "2026.1", "evidence_status": "VERIFIED",
            "provenance_note": "verified technical source", "evidence_refs": ["E-047"],
            "changed_by": "forged-coach", "coach_final_authority": True,
        }),
        ("/api/v1/knowledge-runtime/feat-048/lifecycle", {
            "knowledge_id": "K-1", "lifecycle_status": "APPROVED",
            "changed_by": "forged-coach", "coach_final_authority": True,
        }),
        ("/api/v1/knowledge-runtime/feat-049/retrieve", {
            "workflow_context": "decision diagnosis", "query": "K-1",
            "requested_by": "forged-coach", "coach_final_authority": True,
        }),
        ("/api/v1/knowledge-runtime/feat-050/link", {
            "knowledge_id": "K-1", "unit_id": "UNIT-1", "link_type": "SUPPORTS",
            "evidence_refs": ["E-050"], "linked_by": "forged-coach",
            "coach_final_authority": True,
        }),
    ]
    for path, payload in cases:
        response = client.post(path, json=payload)
        assert response.status_code == 503, (path, response.status_code, response.text)
        assert "temporarily disabled" in response.json()["detail"]

    assert knowledge_runtime.MEMORY_ITEMS == {}
    assert knowledge_runtime.MEMORY_LINKS == []


def test_047_050_fail_closed_even_with_bearer_or_forged_authority():
    path = "/api/v1/knowledge-runtime/feat-047/provenance"
    payload = {
        "knowledge_id": "K-2", "source_type": "IJF", "source_ref": "REF-2",
        "source_version": "v1", "evidence_status": "VERIFIED",
        "provenance_note": "source", "evidence_refs": ["E-2"],
        "changed_by": "forged-coach", "coach_final_authority": False,
    }
    assert client.post(path, json=payload).status_code == 503
    assert client.post(
        path, json={**payload, "coach_final_authority": True},
        headers={"Authorization": "Bearer invalid-token"},
    ).status_code == 503
    assert knowledge_runtime.MEMORY_ITEMS == {}
