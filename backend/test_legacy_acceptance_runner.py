"""Run legacy feature acceptance tests with route guards explicitly overridden.

These tests validate business behavior and are not authorization evidence.
Phase 4 authorization has its own real-route and PostgreSQL denial suites.
The override exists only in this CI runner, never in application runtime.
"""
import runpy
import sys

import main
import persistence
import phase4_route_guard
import phase4_identity_boundary
import phase4_domain_authorization
import backend.main as package_main
from phase4_identity_boundary import Principal

if len(sys.argv) < 2:
    raise SystemExit(
        "usage: python test_legacy_acceptance_runner.py test_feat_XXX.py | "
        "--unittest module.TestCase | --pytest pytest-args..."
    )

tenant_id = "ci-legacy-acceptance"
principal = Principal(
    actor_id="ci|legacy-acceptance",
    role="coach",
    tenant_id=tenant_id,
    resource_owner_id=None,
    verified=True,
    source="oidc_jwt",
)

# Route-specific security tests exercise the real dependencies separately.
# Legacy feature tests use this explicit test-only override to isolate their
# business contract from the new authorization boundary.
main.app.dependency_overrides[phase4_route_guard.require_phase4_tenant_member] = (
    lambda: {"principal": principal, "tenant_id": tenant_id}
)
main.app.dependency_overrides[phase4_route_guard.require_phase4_route_access] = (
    lambda: {
        "principal": principal,
        "tenant_id": tenant_id,
        "athlete_id": None,
        "authorization": {"allowed": True, "test_only_override": True},
    }
)
main.app.dependency_overrides[phase4_identity_boundary.require_phase4_principal] = (
    lambda: principal
)
main.app.dependency_overrides[phase4_domain_authorization.require_phase4_domain_access] = (
    lambda: {"principal": principal, "tenant_id": tenant_id}
)

# Some older acceptance modules import the app as backend.main rather than main.
package_main.app.dependency_overrides.update(main.app.dependency_overrides)

if persistence.is_postgres_enabled():
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_tenants (tenant_id, display_name)
                   VALUES (%s, %s) ON CONFLICT (tenant_id) DO NOTHING""",
                (tenant_id, "CI Legacy Acceptance"),
            )
            cur.execute(
                """INSERT INTO kaizo_tenant_memberships (tenant_id,subject_id,role,status)
                   VALUES (%s,%s,%s,'ACTIVE')
                   ON CONFLICT (tenant_id,subject_id,role)
                   DO UPDATE SET status='ACTIVE',updated_at=NOW()""",
                (tenant_id, principal.actor_id, principal.role),
            )
        conn.commit()

mode = sys.argv[1]
if mode == "--unittest":
    import unittest
    names = sys.argv[2:]
    if not names:
        raise SystemExit("at least one unittest target is required")
    suite = unittest.TestSuite()
    for name in names:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
elif mode == "--pytest":
    import pytest
    raise SystemExit(pytest.main(sys.argv[2:]))
else:
    if len(sys.argv) != 2:
        raise SystemExit("pass exactly one legacy test filename")
    sys.argv = [mode]
    runpy.run_path(mode, run_name="__main__")
