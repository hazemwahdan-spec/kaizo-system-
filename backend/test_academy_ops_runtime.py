"""Fail-closed tests for unscoped FEAT-061..065 Academy routes."""
import os
os.environ["KAIZO_IDENTITY_MODE"] = "production"
os.environ.pop("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", None)

from fastapi.testclient import TestClient
import main
import academy_ops_runtime

client = TestClient(main.app, raise_server_exceptions=False)
FORGED_HEADERS = {
    "X-KAIZO-Actor": "forged-coach",
    "X-KAIZO-Role": "coach",
    "X-KAIZO-Tenant": "forged-tenant",
    "X-KAIZO-Resource-Owner": "forged-athlete",
}


def test_academy_routes_fail_closed_without_verified_tenant_membership():
    for mapping in (
        academy_ops_runtime.ACADEMIES, academy_ops_runtime.MEMBERSHIPS,
        academy_ops_runtime.GROUPS, academy_ops_runtime.ASSIGNMENTS,
    ):
        mapping.clear()
    cases = [
        ("POST", "/api/v1/academy/academies", {"name": "Forged", "owner_id": "forged-owner", "coach_final_authority": True}),
        ("GET", "/api/v1/academy/academies/forged-academy", None),
        ("POST", "/api/v1/academy/memberships", {"academy_id": "forged-academy", "coach_id": "forged-coach", "role": "owner", "coach_final_authority": True}),
        ("POST", "/api/v1/academy/groups", {"academy_id": "forged-academy", "name": "Forged group", "coach_final_authority": True}),
        ("POST", "/api/v1/academy/assignments", {"academy_id": "forged-academy", "athlete_id": "forged-athlete", "coach_ids": ["forged-coach"], "coach_final_authority": True}),
        ("GET", "/api/v1/academy/academies/forged-academy/dashboard", None),
    ]
    for method, path, payload in cases:
        kwargs = {"headers": FORGED_HEADERS}
        if payload is not None:
            kwargs["json"] = payload
        response = client.request(method, path, **kwargs)
        assert response.status_code == 410, (method, path, response.status_code, response.text)
    assert not any((academy_ops_runtime.ACADEMIES, academy_ops_runtime.MEMBERSHIPS,
                    academy_ops_runtime.GROUPS, academy_ops_runtime.ASSIGNMENTS))
