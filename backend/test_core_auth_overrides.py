"""Explicit test-only overrides for legacy feature acceptance scripts.

These overrides are only imported by individual acceptance tests. They are not
used by the production application or Phase 4 security acceptance tests.
"""
import atexit
from unittest.mock import patch

import main
try:
    import backend.main as backend_main
except ImportError:
    backend_main = main

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
_modules = []
for _module in (main, backend_main):
    if all(existing is not _module for existing in _modules):
        _modules.append(_module)
        _module.app.dependency_overrides[require_core_actor] = lambda: _principal

_patches = []
for _module in _modules:
    for _name in (
        "bind_new_resource",
        "assert_resource_tenant",
        "assert_assessment_tenant",
        "assert_minor_consent",
    ):
        _patch = patch(f"{_module.__name__}.{_name}")
        _patch.start()
        _patches.append(_patch)


def cleanup():
    for _module in _modules:
        _module.app.dependency_overrides.pop(require_core_actor, None)
    for _patch in reversed(_patches):
        _patch.stop()


atexit.register(cleanup)
