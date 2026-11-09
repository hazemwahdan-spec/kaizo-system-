import os
os.environ["KAIZO_PERSISTENCE_MODE"]="memory"

from fastapi.testclient import TestClient
from fastapi import HTTPException
import pytest
import main
from main import app
from feature_runtime import CONTRACTS, LEGACY_UNSCOPED_COACH_FEATURES, FeatureRecordRequest, _MEMORY, _validate
import evidence_store
import persistence

client=TestClient(app)

def test_all_missing_features_have_real_contracts():
    expected={f"FEAT-{i:03d}" for i in range(29,76)} - {"FEAT-041","FEAT-046","FEAT-051","FEAT-056"}
    assert set(CONTRACTS)==expected
    for fid, contract in CONTRACTS.items():
        assert contract["name"]
        assert contract["required"]

def test_generic_coach_feature_routes_fail_closed_for_reads_and_writes():
    _MEMORY.clear()
    for feature_id in sorted(LEGACY_UNSCOPED_COACH_FEATURES):
        contract = CONTRACTS[feature_id]
        slug = contract["name"].lower().replace("/", "-").replace(" ", "-")
        slug = "".join(ch for ch in slug if ch.isalnum() or ch == "-").strip("-")
        path = f"/api/v1/features/{feature_id.lower()}/{slug}"
        body = {
            "subject_id": "athlete-1",
            "actor_id": "forged-coach",
            "payload": {"athlete_id": "athlete-1", "decision_id": "forged-decision"},
            "coach_final_authority": True,
            "execution_authorized": False,
        }
        assert client.post(path, json=body).status_code == 410, feature_id
        assert client.get(path).status_code == 410, feature_id
        assert client.get(path + "/legacy-record").status_code == 410, feature_id
    assert _MEMORY == {}

def test_internal_feature_validation_still_requires_evidence():
    req = FeatureRecordRequest(
        subject_id="drill-1",
        actor_id="coach-1",
        payload={
            "drill_id":"D1","name":"uchi-komi","judo_area":"Nage-waza",
            "technical_skill":"Seoi-nage entry","problem_target":"late entry",
            "decision_target":"entry timing","age_suitability":"U11+",
            "skill_level":"intermediate","execution_pattern":"controlled repetitions",
            "kpi":"entry quality","safety_constraints":"coach supervised"
        },
        coach_final_authority=True,
        execution_authorized=False,
    )
    with pytest.raises(HTTPException) as exc:
        _validate("FEAT-031", req)
    assert exc.value.status_code == 400
    assert "at least one evidence reference" in str(exc.value.detail)


def test_canonical_domain_validation_is_enforced():
    # Seed the internal evidence registry for this feature-contract test.
    # Public evidence writes are intentionally denied until verified publisher
    # authorization is deployed; endpoint denial is tested separately.
    evidence = {
        "evidence_id": "RULE-SOURCE-029", "subject_type": "rule",
        "subject_id": "athlete-1", "evidence_level": "E2", "status": "VERIFIED",
        "source_ref": "RULE-REF-029", "claim": "Verified progression-rule source",
        "observed_value": {"threshold": 8}, "verified_by": "trusted-test-fixture",
        "verified_at": "2026-10-18T00:00:00Z", "notes": None,
    }
    # Persistence Adapter Validation runs with PostgreSQL enabled; seed the
    # authoritative test database as well as the in-memory registries.
    persistence.upsert_evidence(evidence)
    main.EVIDENCE_RECORDS[evidence["evidence_id"]] = evidence
    evidence_store.EVIDENCE_RECORDS[evidence["evidence_id"]] = evidence
    rule_req = FeatureRecordRequest(
        subject_id="athlete-1", actor_id="coach-1",
        payload={"metric":"technical_quality","threshold":8,"action":"PROGRESS","adjustment":1,
                 "rule_version":"1.0.0","approval_status":"APPROVED"},
        evidence_refs=["RULE-SOURCE-029"], coach_final_authority=True,
        execution_authorized=False)
    assert _validate("FEAT-029", rule_req)["name"] == "Progression/regression rules"

    drill_req = FeatureRecordRequest(
        subject_id="drill-1", actor_id="coach-1",
        payload={"drill_id":"D1","name":"Uchi-komi","judo_area":"Nage-waza",
        "technical_skill":"Seoi-nage entry","problem_target":"late entry",
        "decision_target":"entry timing","age_suitability":"U11+","skill_level":"intermediate",
        "execution_pattern":"controlled repetitions","kpi":"entry quality",
        "safety_constraints":"coach supervised"},
        evidence_refs=["REF-015"], coach_final_authority=True,
        execution_authorized=False)
    assert _validate("FEAT-031", drill_req)["name"] == "Drill library"

def test_semantic_validation_rejects_invalid_feature_shapes():
    invalid_trend = FeatureRecordRequest(
        subject_id="athlete-1", actor_id="coach-1",
        payload={"athlete_id":"athlete-1","event_ids":["E1"],"trend":"up"},
        evidence_refs=["REF-015"], coach_final_authority=True,
        execution_authorized=False)
    with pytest.raises(HTTPException) as exc:
        _validate("FEAT-069", invalid_trend)
    assert exc.value.status_code == 400
    assert "two events" in str(exc.value.detail)

    invalid_export = FeatureRecordRequest(
        subject_id="report-1", actor_id="coach-1",
        payload={"report_id":"R1","approved_record_ids":["A1"],"format":"XML"},
        coach_final_authority=True, execution_authorized=False)
    with pytest.raises(HTTPException) as exc:
        _validate("FEAT-075", invalid_export)
    assert exc.value.status_code == 400
    assert "format" in str(exc.value.detail)

    bad = client.post("/api/v1/features/feat-039/progress-state-update", json={
        "subject_id":"athlete-1","actor_id":"forged-coach",
        "payload":{"athlete_id":"athlete-1","state":"GUESS","state_basis":"unsupported"},
        "evidence_refs":["REF-015"],"coach_final_authority":True,"execution_authorized":False})
    assert bad.status_code == 410

    invalid_progress = FeatureRecordRequest(
        subject_id="athlete-1", actor_id="coach-1",
        payload={"athlete_id":"athlete-1","state":"GUESS","state_basis":"unsupported"},
        evidence_refs=["REF-015"], coach_final_authority=True,
        execution_authorized=False)
    with pytest.raises(HTTPException) as exc:
        _validate("FEAT-039", invalid_progress)
    assert exc.value.status_code == 400
