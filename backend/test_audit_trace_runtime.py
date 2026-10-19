"""Security containment tests for the Phase 4 audit-trace gate."""
import os

os.environ["KAIZO_PERSISTENCE_MODE"] = "memory"

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_all_audit_trace_mutations_fail_closed_pending_authorization():
    cases = [
        ("/api/v1/audit-trace/feat-052/trace", {"actor_id": "forged-coach", "action": "DECISION_REVIEW", "coach_final_authority": True}),
        ("/api/v1/audit-trace/feat-053/governance", {"object_id": "DEC-1", "object_type": "decision", "governance_status": "REVIEW", "owner": "forged-coach", "coach_final_authority": True}),
        ("/api/v1/audit-trace/feat-054/review", {"query": "DEC-1", "reviewed_by": "forged-coach", "coach_final_authority": True}),
        ("/api/v1/audit-trace/feat-055/trace", {"product_action": "REPORT_GENERATED", "source_record_ids": ["DEC-1"], "trace_reason": "test", "traced_by": "forged-coach", "coach_final_authority": True}),
    ]
    for path, payload in cases:
        response = client.post(path, json=payload)
        assert response.status_code == 503, (path, response.status_code, response.text)
        assert "temporarily disabled" in response.json()["detail"]


def test_audit_trace_rejects_anonymous_and_bearer_requests_until_scoped_controls_exist():
    path = "/api/v1/audit-trace/feat-052/trace"
    payload = {"actor_id": "coach-1", "action": "X", "coach_final_authority": True}
    assert client.post(path, json=payload).status_code == 503
    assert client.post(path, json=payload, headers={"Authorization": "Bearer invalid"}).status_code == 503
