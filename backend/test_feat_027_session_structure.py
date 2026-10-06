from fastapi.testclient import TestClient
import os, uuid
os.environ["KAIZO_PERSISTENCE_MODE"]="postgres"
from backend.main import app

def test_feat_027_session_structure_and_timing():
    client=TestClient(app)
    plan_id="PLAN-027-"+uuid.uuid4().hex[:8]
    athlete_id="ATH-027-"+uuid.uuid4().hex[:8]
    decision_id="DEC-027-"+uuid.uuid4().hex[:8]
    # Seed the minimal durable plan dependency directly through API-shaped persistence state.
    from backend import main
    main.persistence.upsert_training_plan({"plan_id":plan_id,"athlete_id":athlete_id,"decision_id":decision_id,
        "title":"Plan 027","objective":"Session timing","constraints":{},"status":"DRAFT",
        "created_by":"coach-027","created_at":"2026-10-06T00:00:00"})
    r=client.post(f"/api/v1/training-plans/{plan_id}/sessions",json={
        "plan_id":plan_id,"athlete_id":athlete_id,"title":"Session 027","duration_minutes":60,
        "blocks":[{"name":"Warm-up","duration_minutes":15},{"name":"Technical","duration_minutes":30},{"name":"Randori","duration_minutes":15}],
        "created_by":"coach-027"})
    assert r.status_code==201
    session=r.json()
    assert session["duration_minutes"]==60
    assert sum(b["duration_minutes"] for b in session["blocks"])==60
    assert session["coach_final_authority"] is True
    assert session["execution_authorized"] is False
    g=client.get(f"/api/v1/training-sessions/{session['session_id']}")
    assert g.status_code==200
    assert g.json()["title"]=="Session 027"
