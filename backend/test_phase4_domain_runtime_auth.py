"""Regression tests for authentication gates on every Phase 4 domain runtime."""
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from phase4_identity_boundary import require_phase4_principal


def test_domain_runtime_routes_fail_closed_without_verified_principal():
    client = TestClient(main.app)
    previous = main.app.dependency_overrides.pop(require_phase4_principal, None)
    try:
        with patch.dict(os.environ, {"KAIZO_PHASE4_IDENTITY_ENFORCEMENT": "disabled"}):
            requests = [
                ("get", "/api/v1/features/feat-034/drill-prescription"),
                ("post", "/api/v1/knowledge-runtime/feat-047/provenance"),
                ("post", "/api/v1/audit-trace/feat-052/trace"),
                ("post", "/api/v1/evidence-safety/feat-057/evidence-quality"),
                ("get", "/api/v1/reporting/export/not-a-real-report"),
                ("get", "/api/v1/competition/trend/athlete-1?event_ids=e1,e2"),
                ("get", "/api/v1/academy/academies/not-a-real-academy/dashboard"),
            ]
            for method, url in requests:
                response = getattr(client, method)(url, json={} if method == "post" else None) if method == "post" else getattr(client, method)(url)
                assert response.status_code == 503, (method, url, response.status_code, response.text)
    finally:
        if previous is not None:
            main.app.dependency_overrides[require_phase4_principal] = previous
