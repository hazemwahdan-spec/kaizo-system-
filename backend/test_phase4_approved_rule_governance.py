"""Phase 4 rule-governance semantics remain testable internally; the generic
Coach feature route is retired until verified identity and tenant scope exist.
"""
import os

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/kaizo_test"

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
import main
import persistence
import evidence_store
from feature_runtime import FeatureRecordRequest, _validate
from progression_rules import ProgressionRegressionRule

persistence.initialize()
client = TestClient(main.app)
RULE_URL = "/api/v1/features/feat-029/progression-regression-rules"


def payload(evidence_refs=None, **overrides):
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
        "evidence_refs": evidence_refs if evidence_refs is not None else ["P4-RULE-SOURCE-001"],
        "coach_final_authority": True,
        "execution_authorized": False,
    }


def create_rule_evidence(evidence_id, status="VERIFIED", level="E2"):
    record = {
        "evidence_id": evidence_id,
        "subject_type": "rule",
        "subject_id": "P4-RULE-SUBJECT",
        "evidence_level": level,
        "status": status,
        "source_ref": f"SOURCE-{evidence_id}",
        "claim": "Rule evidence validation fixture",
        "observed_value": {"threshold": 5},
        "verified_by": "trusted-test-fixture",
        "verified_at": "2026-10-18T00:00:00Z",
        "notes": None,
    }
    persistence.upsert_evidence(record)
    main.EVIDENCE_RECORDS[evidence_id] = record
    evidence_store.EVIDENCE_RECORDS[evidence_id] = record
    return record


def validate(body):
    return _validate("FEAT-029", FeatureRecordRequest(**body))


def test_generic_rule_endpoint_is_retired_until_verified_coach_scope_exists():
    create_rule_evidence("P4-RULE-SOURCE-001")
    response = client.post(RULE_URL, json=payload())
    assert response.status_code == 410, response.text


def test_approved_versioned_rule_still_passes_internal_governance_validation():
    create_rule_evidence("P4-RULE-SOURCE-001")
    assert validate(payload())["name"] == "Progression/regression rules"


def test_unapproved_rule_is_rejected_by_internal_governance():
    create_rule_evidence("P4-RULE-SOURCE-001")
    with pytest.raises(HTTPException) as exc:
        validate(payload(approval_status="DRAFT"))
    assert exc.value.status_code == 400
    assert "only APPROVED rules may be evaluated" in str(exc.value.detail)


def test_missing_rule_version_and_missing_provenance_are_rejected():
    create_rule_evidence("P4-RULE-SOURCE-001")
    body = payload()
    body["payload"].pop("rule_version")
    with pytest.raises(HTTPException) as exc:
        validate(body)
    assert exc.value.status_code == 400
    assert "rule_version" in str(exc.value.detail)

    no_provenance = payload(evidence_refs=[])
    with pytest.raises(HTTPException) as exc:
        validate(no_provenance)
    assert exc.value.status_code == 400
    assert "evidence_refs are required" in str(exc.value.detail)


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
    with pytest.raises(ValueError, match="only APPROVED rules"):
        rule.evaluate(6)


def test_authority_and_execution_flags_cannot_be_bypassed():
    no_authority = payload()
    no_authority["coach_final_authority"] = False
    with pytest.raises(HTTPException) as exc:
        validate(no_authority)
    assert exc.value.status_code == 409

    autonomous = payload()
    autonomous["execution_authorized"] = True
    with pytest.raises(HTTPException) as exc:
        validate(autonomous)
    assert exc.value.status_code == 409

    # Neither caller-supplied flag can make the retired public route callable.
    assert client.post(RULE_URL, json=no_authority).status_code == 410
    assert client.post(RULE_URL, json=autonomous).status_code == 410


def test_rule_rejects_missing_unverified_or_e0_evidence():
    with pytest.raises(HTTPException) as exc:
        validate(payload(evidence_refs=["P4-RULE-MISSING-EVIDENCE"]))
    assert exc.value.status_code == 404
    assert exc.value.detail["decision_state"] == "HOLD"

    create_rule_evidence("P4-RULE-UNVERIFIED", status="UNVERIFIED", level="E2")
    with pytest.raises(HTTPException) as exc:
        validate(payload(evidence_refs=["P4-RULE-UNVERIFIED"]))
    assert exc.value.status_code == 409
    assert exc.value.detail["decision_state"] == "HOLD"
    assert "not verified" in str(exc.value.detail)

    create_rule_evidence("P4-RULE-E0", status="VERIFIED", level="E0")
    with pytest.raises(HTTPException) as exc:
        validate(payload(evidence_refs=["P4-RULE-E0"]))
    assert exc.value.status_code == 409
    assert exc.value.detail["decision_state"] == "HOLD"
    assert "E0 evidence cannot authorize a progression rule" in str(exc.value.detail)


if __name__ == "__main__":
    test_generic_rule_endpoint_is_retired_until_verified_coach_scope_exists()
    test_approved_versioned_rule_still_passes_internal_governance_validation()
    test_unapproved_rule_is_rejected_by_internal_governance()
    test_missing_rule_version_and_missing_provenance_are_rejected()
    test_direct_rule_evaluation_cannot_bypass_approval()
    test_authority_and_execution_flags_cannot_be_bypassed()
    test_rule_rejects_missing_unverified_or_e0_evidence()
    print("Phase 4 approved-rule governance acceptance passed")
