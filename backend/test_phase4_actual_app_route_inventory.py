"""Actual Core app route inventory for Phase 4 security work.

This is a diagnostic baseline, not a security acceptance test. It imports the
real backend.main:app (including mounted routers and dynamically generated
feature routes), inventories registered HTTP routes and their dependency trees,
and pins representative sensitive routes as currently missing the Phase 4
verified-principal dependency. When route enforcement is implemented, replace
the baseline assertions with positive acceptance assertions for auth, role,
server-loaded tenant/resource ownership, consent, and no-write-on-deny.
"""
import sys
from pathlib import Path

from fastapi.routing import APIRoute

# Core modules use the backend directory as their import root in deployment.
# Put it on sys.path before importing backend.main so this test mirrors that
# module layout when pytest is launched from the repository root.
_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from backend import main as core_main
from backend import phase4_core_resource_authorization as authz


def _dependency_functions(dependant):
    """Return dependency callables recursively for a registered route."""
    functions = set()
    for child in dependant.dependencies:
        if child.call is not None:
            functions.add(child.call)
        functions.update(_dependency_functions(child))
    return functions


def _registered_http_routes():
    rows = []
    for route in core_main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted((route.methods or set()) - {"HEAD", "OPTIONS"})
        if not methods:
            continue
        rows.append(
            {
                "path": route.path,
                "methods": methods,
                "name": route.name,
                "dependencies": _dependency_functions(route.dependant),
            }
        )
    return rows


def test_actual_core_app_route_inventory_includes_sensitive_and_generated_routes():
    rows = _registered_http_routes()
    identities = {(method, row["path"]) for row in rows for method in row["methods"]}

    # These assertions target the actual application, not a synthetic harness.
    assert ("POST", "/api/v1/athletes") in identities
    assert ("GET", "/api/v1/athletes/{athlete_id}") in identities
    assert ("POST", "/api/v1/assessments") in identities
    assert ("GET", "/api/v1/assessments/{assessment_id}") in identities
    assert any(path.startswith("/api/v1/features") for _, path in identities)
    assert ("POST", "/api/v1/state-cycle/feat-042/digital-twin-state") in identities


def test_actual_core_app_sensitive_routes_are_wired_to_phase4_identity_and_scope():
    rows = _registered_http_routes()
    by_route = {(method, row["path"]): row for row in rows for method in row["methods"]}
    sensitive_baseline = [
        ("POST", "/api/v1/athletes"),
        ("GET", "/api/v1/athletes/{athlete_id}"),
        ("PATCH", "/api/v1/athletes/{athlete_id}"),
        ("POST", "/api/v1/assessments"),
        ("GET", "/api/v1/assessments/{assessment_id}"),
    ]

    assert all(key in by_route for key in sensitive_baseline)
    # Explicitly pins the known gap so this file cannot be mistaken for proof
    # of protection. This expectation must be inverted when real wiring lands.
    assert all(
        boundary.require_phase4_principal not in by_route[key]["dependencies"]
        for key in sensitive_baseline
    )
