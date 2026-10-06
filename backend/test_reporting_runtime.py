from fastapi.testclient import TestClient
import reporting_runtime as runtime


def setup_function():
    runtime.PROGRESS.clear()
    runtime.KPI_TRENDS.clear()
    runtime.COACH_SUMMARIES.clear()
    runtime.ACADEMY_DASHBOARDS.clear()
    runtime.EXPORTS.clear()


def test_reporting_cycle_and_approved_export():
    client=TestClient(__import__("main").app)

    p=client.post("/api/v1/reporting/progress",json={
        "athlete_id":"a1","period":"2026-Q4",
        "progress":{"state":"IMPROVING","delta":8},"recorded_by":"coach"
    })
    assert p.status_code==201

    k=client.post("/api/v1/reporting/kpi-trend",json={
        "athlete_id":"a1","kpi_id":"randori_transfer","period":"2026-Q4",
        "trend":{"direction":"UP","delta":12},"recorded_by":"coach"
    })
    assert k.status_code==201

    c=client.post("/api/v1/reporting/coach-summary",json={
        "coach_id":"coach","period":"2026-Q4",
        "summary":{"decision_cycles":24,"quality_rate":0.91},"recorded_by":"coach"
    })
    assert c.status_code==201

    d=client.post("/api/v1/reporting/academy-dashboard",json={
        "academy_id":"academy","period":"2026-Q4",
        "metrics":{"active_athletes":18,"active_coaches":4},"recorded_by":"coach"
    })
    assert d.status_code==201

    records=[
        {"record_id":"r1","approval_status":"APPROVED","type":"progress","value":8},
        {"record_id":"r2","approval_status":"APPROVED","type":"kpi","value":12},
    ]
    export=client.post("/api/v1/reporting/export",json={
        "approved_record_ids":["r1","r2"],"format":"CSV",
        "records":records,"requested_by":"coach"
    })
    assert export.status_code==201
    body=export.json()
    assert body["record_count"]==2
    assert "record_id" in body["content"]
    assert body["execution_authorized"] is False


def test_export_rejects_unapproved_data():
    client=TestClient(__import__("main").app)
    response=client.post("/api/v1/reporting/export",json={
        "approved_record_ids":["r1"],"format":"JSON",
        "records":[{"record_id":"r1","approval_status":"PENDING"}],
        "requested_by":"coach"
    })
    assert response.status_code==409


def test_export_requires_explicit_approval_ids():
    client=TestClient(__import__("main").app)
    response=client.post("/api/v1/reporting/export",json={
        "approved_record_ids":["r1"],"format":"JSON",
        "records":[{"record_id":"r2","approval_status":"APPROVED"}],
        "requested_by":"coach"
    })
    assert response.status_code==409


def test_authority_gate_applies_to_reporting():
    client=TestClient(__import__("main").app)
    response=client.post("/api/v1/reporting/progress",json={
        "athlete_id":"a","period":"2026-Q4","progress":{"x":1},
        "recorded_by":"coach","coach_final_authority":False
    })
    assert response.status_code==409
