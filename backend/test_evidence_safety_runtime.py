"""Fail-closed tests for unscoped FEAT-057..060 evidence-safety routes."""
import os
os.environ["KAIZO_IDENTITY_MODE"] = "production"
os.environ.pop("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", None)

from fastapi.testclient import TestClient
import main
import evidence_safety_runtime

client = TestClient(main.app, raise_server_exceptions=False)
FORGED_HEADERS = {
    "X-KAIZO-Actor": "forged-coach",
    "X-KAIZO-Role": "coach",
    "X-KAIZO-Tenant": "forged-tenant",
    "X-KAIZO-Resource-Owner": "forged-athlete",
}


def test_evidence_safety_routes_fail_closed_without_verified_scope():
    evidence_safety_runtime.MEMORY.clear()
    cases = [
        ("/api/v1/evidence-safety/feat-057/evidence-quality", {
            "subject_id": "forged-athlete", "evidence_level": "E3",
            "quality_status": "VERIFIED", "evidence_refs": ["REF-FORGED"],
            "assessed_by": "forged-coach", "coach_final_authority": True,
        }),
        ("/api/v1/evidence-safety/feat-058/provenance", {
            "subject_id": "forged-athlete", "provenance_refs": ["REF-FORGED"],
            "disclosed_by": "forged-coach", "coach_final_authority": True,
        }),
        ("/api/v1/evidence-safety/feat-059/block", {
            "action_id": "forged-action", "block_reason": "forged",
            "diagnostic": {"athlete_id": "forged-athlete"}, "evidence_refs": ["REF-FORGED"],
            "blocked_by": "forged-coach", "coach_final_authority": True,
        }),
        ("/api/v1/evidence-safety/feat-060/escalate", {
            "subject_id": "forged-athlete", "escalation_reason": "forged",
            "review_state": "OPEN", "escalated_by": "forged-coach",
            "coach_final_authority": True,
        }),
    ]
    for path, payload in cases:
        response = client.post(path, json=payload, headers=FORGED_HEADERS)
        assert response.status_code == 410, (path, response.status_code, response.text)
    assert evidence_safety_runtime.MEMORY == []
