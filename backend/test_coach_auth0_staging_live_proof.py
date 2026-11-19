"""Offline contract tests for the guarded Auth0 Staging live-proof harness."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_coach_auth0_staging.py"
SPEC = importlib.util.spec_from_file_location("coach_auth0_staging_harness", SCRIPT)
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def _configure(monkeypatch, *, foreign_coach="foreign-coach-athlete",
               foreign_tenant="foreign-tenant-athlete"):
    values = {
        "KAIZO_STAGING_API_URL": "https://staging-api.example",
        "KAIZO_STAGING_API_HOST": "staging-api.example",
        "KAIZO_PRODUCTION_API_HOST": "production-api.example",
        "KAIZO_OIDC_BEARER_TOKEN": "disposable-test-token",
        "KAIZO_STAGING_OWNED_ATHLETE_ID": "owned-athlete",
        "KAIZO_STAGING_FOREIGN_COACH_ATHLETE_ID": foreign_coach,
        "KAIZO_STAGING_FOREIGN_TENANT_ATHLETE_ID": foreign_tenant,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    for key in (
        "KAIZO_OIDC_NO_PRODUCT_TOKEN",
        "KAIZO_OIDC_NONCOACH_TOKEN",
        "KAIZO_OIDC_WRONG_AUDIENCE_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)


def test_live_proof_requires_two_distinct_foreign_scope_athletes(monkeypatch):
    _configure(monkeypatch, foreign_coach="")
    with pytest.raises(RuntimeError, match="Separate foreign-Coach and foreign-tenant"):
        harness.main()


@pytest.mark.parametrize(
    ("foreign_coach", "foreign_tenant"),
    [
        ("owned-athlete", "foreign-tenant-athlete"),
        ("foreign-coach-athlete", "owned-athlete"),
        ("same-foreign-athlete", "same-foreign-athlete"),
    ],
)
def test_live_proof_rejects_duplicate_scope_test_ids(monkeypatch, foreign_coach, foreign_tenant):
    _configure(monkeypatch, foreign_coach=foreign_coach, foreign_tenant=foreign_tenant)
    with pytest.raises(RuntimeError, match="must be distinct"):
        harness.main()


def test_live_proof_checks_same_tenant_foreign_coach_and_foreign_tenant_denials(monkeypatch):
    _configure(monkeypatch)
    calls = []

    def fake_request(base, path, token=None, extra_headers=None):
        calls.append((path, token, extra_headers))
        if path == "/api/v1/product/auth/oidc/verify":
            return 200, {"verified": True, "source": "oidc_jwt"}
        if path == "/api/v1/product/coach/athletes":
            if token == "disposable-test-token":
                return 200, {"athletes": [{"athlete_id": "owned-athlete"}]}
            return 401, {}
        if path.endswith("/owned-athlete"):
            return 200, {"athlete_id": "owned-athlete"}
        if path.endswith("/foreign-coach-athlete"):
            return 404, {}
        if path.endswith("/foreign-tenant-athlete"):
            return 404, {}
        return 404, {}

    monkeypatch.setattr(harness, "request", fake_request)
    harness.main()

    paths = [path for path, _token, _headers in calls]
    assert "/api/v1/product/coach/athletes/foreign-coach-athlete" in paths
    assert "/api/v1/product/coach/athletes/foreign-tenant-athlete" in paths
