"""Phase 4 input provenance acceptance: version, status and fail-closed lifecycle."""
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


def provenance(status="VERIFIED", **overrides):
    suffix = uuid.uuid4().hex[:8]
    body = {
        "knowledge_id": f"P4-KNOWLEDGE-{suffix}",
        "source_type": "IJF",
        "source_ref": "P4-SOURCE-001",
        "source_version": "2026.1",
        "evidence_status": status,
        "provenance_note": "Versioned source with explicit evidence status",
        "evidence_refs": ["P4-EVIDENCE-001"],
        "changed_by": "phase4-provenance-test",
        "coach_final_authority": True,
    }
    body.update(overrides)
    return body


def test_phase4_verified_versioned_provenance_roundtrips():
    body = provenance()
    response = client.post(f"{BASE}/feat-047/provenance", json=body)
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["source_version"] == "2026.1"
    assert record["evidence_status"] == "VERIFIED"
    assert record["evidence_refs"] == ["P4-EVIDENCE-001"]
    assert record["execution_authorized"] is False

    lifecycle = client.post(f"{BASE}/feat-048/lifecycle", json={
        "knowledge_id": body["knowledge_id"],
        "lifecycle_status": "APPROVED",
        "changed_by": "phase4-provenance-test",
        "coach_final_authority": True,
    })
    assert lifecycle.status_code == 200, lifecycle.text

    readback = persistence.load_knowledge().get(body["knowledge_id"])
    assert readback is not None
    assert readback["source_version"] == "2026.1"
    assert readback["evidence_status"] == "VERIFIED"


def test_phase4_unverified_or_conflicting_evidence_cannot_be_approved():
    for status in ("UNVERIFIED", "STALE", "CONFLICTED", "REJECTED", "REVIEW_REQUIRED"):
        body = provenance(status=status)
        created = client.post(f"{BASE}/feat-047/provenance", json=body)
        assert created.status_code == 201, (status, created.text)
        approved = client.post(f"{BASE}/feat-048/lifecycle", json={
            "knowledge_id": body["knowledge_id"],
            "lifecycle_status": "APPROVED",
            "changed_by": "phase4-provenance-test",
            "coach_final_authority": True,
        })
        assert approved.status_code == 409, (status, approved.text)
        assert "evidence_status must be VERIFIED" in approved.text


def test_phase4_missing_version_or_invalid_status_fails_closed():
    missing_version = provenance()
    missing_version.pop("source_version")
    response = client.post(f"{BASE}/feat-047/provenance", json=missing_version)
    assert response.status_code == 422

    invalid_status = provenance(evidence_status="TRUST_ME")
    response = client.post(f"{BASE}/feat-047/provenance", json=invalid_status)
    assert response.status_code == 400
    assert "evidence_status" in response.text


def test_phase4_retrieval_excludes_stale_approved_legacy_record():
    # Simulate a legacy/inconsistent persisted record: retrieval must not promote it.
    record = provenance(evidence_status="STALE")
    knowledge_runtime.MEMORY_ITEMS[record["knowledge_id"]] = {
        **record,
        "lifecycle_status": "APPROVED",
        "created_at": "2026-10-11T00:00:00+00:00",
        "updated_at": "2026-10-11T00:00:00+00:00",
    }
    response = client.post(f"{BASE}/feat-049/retrieve", json={
        "workflow_context": "Phase 4 decision",
        "query": record["knowledge_id"],
        "requested_by": "phase4-provenance-test",
        "coach_final_authority": True,
    })
    assert response.status_code == 200, response.text
    ids = [item.get("knowledge_id") for item in response.json()["results"]]
    assert record["knowledge_id"] not in ids


if __name__ == "__main__":
    test_phase4_verified_versioned_provenance_roundtrips()
    test_phase4_unverified_or_conflicting_evidence_cannot_be_approved()
    test_phase4_missing_version_or_invalid_status_fails_closed()
    test_phase4_retrieval_excludes_stale_approved_legacy_record()
    print("Phase 4 provenance acceptance passed")
