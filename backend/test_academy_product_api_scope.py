"""Product API boundary tests for the read-only Academy-assigned Coach roster."""
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from fastapi import HTTPException

from productization import product_api


def _principal(*, verified=True, source="oidc_jwt"):
    return SimpleNamespace(
        actor_id="coach-from-token",
        role="coach",
        tenant_id="tenant-from-token",
        resource_owner_id=None,
        verified=verified,
        source=source,
    )


def test_academy_roster_route_is_registered_as_read_only_get():
    matches = [
        route for route in product_api.router.routes
        if getattr(route, "path", None) == "/api/v1/product/coach/academies/{academy_id}/athletes"
    ]
    assert len(matches) == 1
    assert matches[0].methods == {"GET"}


def test_academy_roster_rejects_unverified_development_identity(monkeypatch):
    monkeypatch.setattr(product_api, "_coach_scope", lambda *_args: _principal(
        verified=False, source="development_headers"
    ))
    with pytest.raises(HTTPException) as exc:
        product_api.list_academy_assigned_coach_athletes(
            "academy-request", authorization=None, actor_id="spoofed",
            role="coach", tenant_id="spoofed-tenant", owner=None,
        )
    assert exc.value.status_code == 403


def test_academy_roster_uses_verified_principal_scope(monkeypatch):
    principal = _principal()
    captured = {}

    monkeypatch.setattr(product_api, "_coach_scope", lambda *_args: principal)

    def list_assigned(**kwargs):
        captured.update(kwargs)
        return [{
            "athlete_id": "assigned-athlete",
            "display_name": "Assigned Athlete",
            "status": "ACTIVE",
            "academy_id": "academy-request",
            "enrolment_status": "ACTIVE",
            "assignment_status": "ACTIVE",
        }]

    monkeypatch.setattr(
        product_api.academy_tenant_contract,
        "list_assigned_athletes_for_coach",
        list_assigned,
    )
    result = product_api.list_academy_assigned_coach_athletes(
        "academy-request", authorization="Bearer verified",
        actor_id="spoofed", role="academy", tenant_id="spoofed-tenant",
        owner="spoofed-owner",
    )

    assert captured == {
        "tenant_id": "tenant-from-token",
        "academy_id": "academy-request",
        "coach_actor_id": "coach-from-token",
    }
    assert result["total"] == 1
    assert result["athletes"][0]["athlete_id"] == "assigned-athlete"
    assert result["access_scope"] == "active_academy_assignment"
    assert result["longitudinal_access_granted"] is False


def test_academy_roster_fails_closed_without_postgres(monkeypatch):
    monkeypatch.setattr(product_api, "_coach_scope", lambda *_args: _principal())

    def unavailable(**_kwargs):
        raise RuntimeError("Academy roster requires PostgreSQL")

    monkeypatch.setattr(
        product_api.academy_tenant_contract,
        "list_assigned_athletes_for_coach",
        unavailable,
    )
    with pytest.raises(HTTPException) as exc:
        product_api.list_academy_assigned_coach_athletes(
            "academy-request", authorization="Bearer verified",
        )
    assert exc.value.status_code == 503
