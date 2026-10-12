from fastapi.testclient import TestClient
import os
import uuid

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"

from backend.main import app
from backend import main as package_main
from backend.phase4_identity_boundary import Principal
from backend import phase4_route_guard

# This is a legacy business-contract acceptance test, not authorization
# evidence. The real route guards are covered by the dedicated Phase 4
# identity/tenant/consent suites in persistence-adapter-validation.yml.
# Keep the override local to this test process only; never application runtime.
_ci_principal = Principal(
    actor_id="ci|feat-028",
    role="coach",
    tenant_id="ci-feat-028",
    resource_owner_id=None,
    verified=True,
    source="oidc_jwt",
)
app.dependency_overrides[phase4_route_guard.require_phase4_tenant_member] = (
    lambda: {"principal": _ci_principal, "tenant_id": "ci-feat-028"}
)
app.dependency_overrides[phase4_route_guard.require_phase4_route_access] = (
    lambda: {
        "principal": _ci_principal,
        "tenant_id": "ci-feat-028",
        "athlete_id": None,
        "authorization": {"allowed": True, "test_only_override": True},
    }
)
package_main.app.dependency_overrides.update(app.dependency_overrides)


def test_feat_028_dosage_reps_sets():
    client = TestClient(app)
    plan_id = "PLAN-028-" + uuid.uuid4().hex[:8]
    athlete_id = "ATH-028-" + uuid.uuid4().hex[:8]
    decision_id = "DEC-028-" + uuid.uuid4().hex[:8]

    from backend import main
    main.persistence.upsert_training_plan({
        "plan_id": plan_id,
        "athlete_id": athlete_id,
        "decision_id": decision_id,
        "title": "Plan 028",
        "objective": "Dosage prescription",
        "constraints": {},
        "status": "DRAFT",
        "created_by": "coach-028",
        "created_at": "2026-10-06T00:00:00",
    })

    session = client.post(
        f"/api/v1/training-plans/{plan_id}/sessions",
        json={
            "plan_id": plan_id,
            "athlete_id": athlete_id,
            "title": "Session 028",
            "duration_minutes": 60,
            "blocks": [
                {"name": "Technical", "duration_minutes": 40},
                {"name": "Randori", "duration_minutes": 20},
            ],
            "created_by": "coach-028",
        },
    )
    assert session.status_code == 201
    session_id = session.json()["session_id"]

    dosage = client.post(
        f"/api/v1/training-sessions/{session_id}/dosage",
        json={
            "session_id": session_id,
            "block_name": "Technical",
            "sets": 4,
            "reps": 8,
            "rest_seconds": 45,
            "dosage_notes": "Quality entries before speed.",
            "prescribed_by": "coach-028",
        },
    )
    assert dosage.status_code == 201
    body = dosage.json()
    assert body["sets"] == 4
    assert body["reps"] == 8
    assert body["rest_seconds"] == 45
    assert body["status"] == "DRAFT"
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False

    fetched = client.get(f"/api/v1/training-dosages/{body['dosage_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["block_name"] == "Technical"

    listed = client.get(f"/api/v1/training-sessions/{session_id}/dosage")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    invalid = client.post(
        f"/api/v1/training-sessions/{session_id}/dosage",
        json={
            "session_id": session_id,
            "block_name": "Unknown",
            "sets": 3,
            "reps": 5,
            "prescribed_by": "coach-028",
        },
    )
    assert invalid.status_code == 400
