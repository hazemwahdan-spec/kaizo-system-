"""Actual app route inventory and Phase 4 identity-gate coverage acceptance tests.

This imports the real backend.main:app, including mounted routers and dynamic
feature routes. All non-public API routes outside the separately governed
Commercial Product router must require the shared fail-closed identity gate.
Resource ownership and consent coverage are separately tested for the five
Core athlete/assessment handlers; other routes remain a Phase 4 closure blocker
until their resource mapping is implemented and independently tested.
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
import phase4_core_resource_authorization as authz


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
    # The five Core handlers must depend on the shared fail-closed authorization gate.
    assert all(
        authz.require_core_actor in by_route[key]["dependencies"]
        for key in sensitive_baseline
    )


def test_all_sensitive_non_product_api_routes_require_phase4_identity_gate():
    rows = _registered_http_routes()
    unprotected = []
    for row in rows:
        if not row["path"].startswith("/api/v1"):
            continue
        if row["path"] == "/api/v1/health" or row["path"].startswith("/api/v1/product/"):
            continue
        if authz.require_core_actor not in row["dependencies"]:
            unprotected.append((row["methods"], row["path"], row["name"]))
    assert unprotected == [], f"Sensitive API routes without identity gate: {unprotected}"


def test_all_mounted_and_generated_routes_require_fail_closed_resource_scope_guard():
    from backend.main import require_router_resource_scope

    rows = _registered_http_routes()
    mounted_prefixes = (
        "/api/v1/features",
        "/api/v1/training-workflow",
        "/api/v1/knowledge-runtime",
        "/api/v1/audit-trace",
        "/api/v1/evidence-safety",
        "/api/v1/state-cycle",
        "/api/v1/reporting",
        "/api/v1/competition",
        "/api/v1/academy",
    )
    missing_scope_guard = []
    for row in rows:
        if any(row["path"].startswith(prefix) for prefix in mounted_prefixes):
            if require_router_resource_scope not in row["dependencies"]:
                missing_scope_guard.append((row["methods"], row["path"], row["name"]))
    assert missing_scope_guard == [], (
        "Mounted/generated routes without fail-closed resource scope guard: "
        f"{missing_scope_guard}"
    )


def test_problem_library_routes_are_registered_exactly_once():
    """Duplicate FastAPI registrations shadow later handlers and are not acceptable."""
    from collections import Counter

    rows = _registered_http_routes()
    counts = Counter(
        (method, row["path"])
        for row in rows
        for method in row["methods"]
        if row["path"] in {
            "/api/v1/problem-library",
            "/api/v1/problem-library/selections",
            "/api/v1/problem-library/selections/{selection_id}",
        }
    )
    assert counts[("GET", "/api/v1/problem-library")] == 1
    assert counts[("POST", "/api/v1/problem-library/selections")] == 1
    assert counts[("GET", "/api/v1/problem-library/selections/{selection_id}")] == 1


def test_manifest_covers_every_registered_core_api_route():
    """A newly mounted or generated API route cannot escape the closure inventory."""
    import re

    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = (
        repo_root / "docs" / "audits"
        / "KAIZO_PHASE4_ROUTE_RESOURCE_AUTHORIZATION_MANIFEST_20261013.md"
    )
    manifest = manifest_path.read_text(encoding="utf-8")
    documented = set()
    for line in manifest.splitlines():
        match = re.match(
            r"^\|\s*(?:(?:\d+)\s*\|\s*)?"
            r"(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`([^`]+)`\s*\|",
            line,
        )
        if match:
            method, path = match.groups()
            if path == "/api/v1/health" or path.startswith("/api/v1/product/") or path.startswith("/api/v1/features/"):
                continue
            documented.add((method, path))

    actual = set()
    for row in _registered_http_routes():
        path = row["path"]
        if not path.startswith("/api/v1/"):
            continue
        if (
            path == "/api/v1/health"
            or path.startswith("/api/v1/product/")
            or path.startswith("/api/v1/features/")
        ):
            # Generated feature records are dynamically registered; their
            # security contract is checked against the dedicated pattern table below.
            continue
        for method in row["methods"]:
            actual.add((method, path))

    generated_contracts = (
        ("POST", "/api/v1/features/{feature_id}/{slug}"),
        ("GET", "/api/v1/features/{feature_id}/{slug}"),
        ("GET", "/api/v1/features/{feature_id}/{slug}/{record_id}"),
    )
    assert "## Dynamic generated-feature routes" in manifest
    for method, pattern in generated_contracts:
        expected = "| " + method + " | `" + pattern + "` |"
        assert expected in manifest, (
            "Generated feature route pattern missing from manifest: "
            + repr((method, pattern))
        )

    missing = sorted(actual - documented)
    stale = sorted(documented - actual)
    assert not missing, (
        "Registered Core API routes missing from the Phase 4 manifest: "
        f"{missing}"
    )
    assert not stale, (
        "Manifest routes not registered in the actual FastAPI app (update the "
        f"manifest when routes are intentionally removed): {stale}"
    )
