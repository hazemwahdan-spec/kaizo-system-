"""Fail-closed tests for unscoped FEAT-071..075 reporting routes."""
import os
os.environ["KAIZO_IDENTITY_MODE"] = "production"
os.environ.pop("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", None)

from fastapi.testclient import TestClient
import main
import reporting_runtime

client = TestClient(main.app, raise_server_exceptions=False)
FORGED_HEADERS = {
    "X-KAIZO-Actor": "forged-coach",
    "X-KAIZO-Role": "coach",
    "X-KAIZO-Tenant": "forged-tenant",
    "X-KAIZO-Resource-Owner": "forged-athlete",
}


def test_reporting_routes_fail_closed_without_verified_athlete_or_academy_scope():
    for mapping in (
        reporting_runtime.PROGRESS, reporting_runtime.KPI_TRENDS,
        reporting_runtime.COACH_SUMMARIES, reporting_runtime.ACADEMY_DASHBOARDS,
        reporting_runtime.EXPORTS,
    ):
        mapping.clear()
    cases = [
        ("POST", "/api/v1/reporting/progress", {"athlete_id": "forged-athlete", "period": "2026", "progress": {"status": "UP"}, "recorded_by": "forged-coach", "coach_final_authority": True}),
        ("POST", "/api/v1/reporting/kpi-trend", {"athlete_id": "forged-athlete", "kpi_id": "KPI-1", "period": "2026", "trend": {"value": 1}, "recorded_by": "forged-coach", "coach_final_authority": True}),
        ("POST", "/api/v1/reporting/coach-summary", {"coach_id": "forged-coach", "period": "2026", "summary": {"status": "UP"}, "recorded_by": "forged-coach", "coach_final_authority": True}),
        ("POST", "/api/v1/reporting/academy-dashboard", {"academy_id": "forged-academy", "period": "2026", "metrics": {"count": 1}, "recorded_by": "forged-coach", "coach_final_authority": True}),
        ("POST", "/api/v1/reporting/export", {"approved_record_ids": ["FORGED"], "format": "CSV", "records": [{"approval_status": "APPROVED"}], "requested_by": "forged-coach", "coach_final_authority": True}),
        ("GET", "/api/v1/reporting/export/forged-report", None),
    ]
    for method, path, payload in cases:
        kwargs = {"headers": FORGED_HEADERS}
        if payload is not None:
            kwargs["json"] = payload
        response = client.request(method, path, **kwargs)
        assert response.status_code == 410, (method, path, response.status_code, response.text)
    assert not any((reporting_runtime.PROGRESS, reporting_runtime.KPI_TRENDS,
                    reporting_runtime.COACH_SUMMARIES, reporting_runtime.ACADEMY_DASHBOARDS,
                    reporting_runtime.EXPORTS))
