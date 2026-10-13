"""Explicit test-only overrides for legacy feature acceptance scripts.

These overrides must only be imported by individual acceptance tests. They are
not used by the production application or Phase 4 security acceptance tests.
"""
import atexit
from unittest.mock import patch

import main
from phase4_core_resource_authorization import require_core_actor
from productization.identity import Principal

_principal = Principal(
    actor_id="unit-test-coach",
    role="coach",
    tenant_id="unit-test-academy",
    resource_owner_id=None,
    verified=True,
    source="test_override",
)
main.app.dependency_overrides[require_core_actor] = lambda: _principal
_patches = [
    patch("main.bind_new_resource"),
    patch("main.assert_resource_tenant"),
    patch("main.assert_assessment_tenant"),
    patch("main.assert_minor_consent"),
]
for _patch in _patches:
    _patch.start()


def cleanup():
    main.app.dependency_overrides.pop(require_core_actor, None)
    for item in reversed(_patches):
        item.stop()


atexit.register(cleanup)
