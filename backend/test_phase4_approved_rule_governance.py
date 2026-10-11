"""Phase 4 acceptance for versioned, approved rule governance."""
import os

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/kaizo_test"

from fastapi.testclient import TestClient
import main
import persistence
from progression_rules import ProgressionRegressionRule

persistence.initialize()
client = TestClient(main.app)
RULE_URL = "/api/v1/features/feat-029/progression-regression-rules"


def payload(**overrides):
    body = {
        "metric": "entry_timing_score",
        "threshold": 5,
        "operator": "GTE",
        "action": "PROGRESS",
        "adjustment": 1,
        "rule_version": "1.0.0",
        "approval_status": "APPROVED",
    }
    body.update(overrides)
    return {
        "subject_id": "P4-RULE-SUBJECT",
        "actor_id": "phase4-rule-test",
        "payload": body,
        "evidence_refs": ["P4-RULE-SOURCE-001"],
        "coach_final_authority": True,
        "execution_authorized": False,
    }


def test_approved_versioned_rule_is_recorded_without_authorizing_execution():
    response = client.post(RULE_URL, json=payload())
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["feature_id"] == "FEAT-029"
    assert record["payload"]["rule_version"] == "1.0.0"
    assert record["payload"]["approval_status"] == "APPROVED"
    assert record["evidence_refs"] == ["P4-RULE-SOURCE-001"]
    assert record["coach_final_authority"] is True
    assert record["execution_authorized"] is False


def test_unapproved_rule_is_rejected():
    response = client.post(RULE_URL, json=payload(approval_status="DRAFT"))
    assert response.status_code == 400
    assert "only APPROVED rules may be evaluated" in response.text


def test_missing_rule_version_and_missing_provenance_are_rejected():
    body = payload()
    body["payload"].pop("rule_version")
    missing_version = client.post(RULE_URL, json=body)
    assert missing_version.status_code == 400
    assert "rule_version" in missing_version.text

    no_provenance = client.post(RULE_URL, json=payload())
    # FEAT-029 requires evidence refs at the contract boundary.
    no_provenance_payload = payload()
    no_provenance_payload["evidence_refs"] = []
    no_provenance = client.post(RULE_URL, json=no_provenance_payload)
    assert no_provenance.status_code == 400
    assert "evidence_refs" in no_provenance.text


def test_direct_rule_evaluation_cannot_bypass_approval():
    rule = ProgressionRegressionRule(
        rule_id="P4-RULE-DIRECT",
        name="Direct evaluation test",
        metric="entry_timing_score",
        operator="GTE",
        threshold=5,
        action="PROGRESS",
        adjustment=1,
        created_by="phase4-rule-test",
        rule_version="1.0.0",
        approval_status="DRAFT",
    )
    try:
        rule.evaluate(6)
    except ValueError as exc:
        assert "only APPROVED rules" in str(exc)
    else:
        raise AssertionError("unapproved rule evaluation must fail closed")


def test_authority_and_execution_flags_cannot_be_bypassed():
    no_authority = payload()
    no_authority["coach_final_authority"] = False
    response = client.post(RULE_URL, json=no_authority)
    assert response.status_code == 409

    autonomous = payload()
    autonomous["execution_authorized"] = True
    response = client.post(RULE_URL, json=autonomous)
    assert response.status_code == 409


if __name__ == "__main__":
    test_approved_versioned_rule_is_recorded_without_authorizing_execution()
    test_unapproved_rule_is_rejected()
    test_missing_rule_version_and_missing_provenance_are_rejected()
    test_direct_rule_evaluation_cannot_bypass_approval()
    test_authority_and_execution_flags_cannot_be_bypassed()
    print("Phase 4 approved-rule governance acceptance passed")
