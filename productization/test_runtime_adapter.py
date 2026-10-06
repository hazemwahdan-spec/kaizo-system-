from productization.runtime_adapter import (
    ProductCoreRuntimeAdapter,
    RuntimeAuthorizationError,
    RuntimeContext,
)


class FakeCore:
    def request_decision(self, **kwargs):
        return kwargs

    def record_intervention(self, **kwargs):
        return kwargs

    def export_approved(self, **kwargs):
        return kwargs


def test_request_never_authorizes_execution():
    a = ProductCoreRuntimeAdapter(FakeCore())
    out = a.request_decision(
        RuntimeContext("u1", "coach", "academy-a", "athlete-1"),
        "academy-a",
        {"decision": "adapt"},
    )
    assert out["execution_authorized"] is False


def test_cross_tenant_access_is_denied():
    a = ProductCoreRuntimeAdapter(FakeCore())
    try:
        a.request_decision(
            RuntimeContext("u1", "coach", "academy-a"),
            "academy-b",
            {},
        )
        assert False
    except RuntimeAuthorizationError as exc:
        assert "cross-tenant" in str(exc)


def test_coach_mutation_requires_explicit_approval():
    a = ProductCoreRuntimeAdapter(FakeCore())
    try:
        a.record_intervention(
            RuntimeContext("u1", "coach", "academy-a", "athlete-1", False),
            "academy-a",
            {"intervention": "drill"},
        )
        assert False
    except RuntimeAuthorizationError as exc:
        assert "Coach approval" in str(exc)


def test_athlete_cannot_record_intervention():
    a = ProductCoreRuntimeAdapter(FakeCore())
    try:
        a.record_intervention(
            RuntimeContext("u1", "athlete", "academy-a", "u1"),
            "academy-a",
            {"intervention": "drill"},
        )
        assert False
    except RuntimeAuthorizationError:
        pass


def test_export_passes_approved_ids_and_never_authorizes_execution():
    a = ProductCoreRuntimeAdapter(FakeCore())
    out = a.export_approved(
        RuntimeContext("u1", "coach", "academy-a", coach_approved=True),
        "academy-a",
        ["R1", "R2"],
    )
    assert out["approved_record_ids"] == ["R1", "R2"]
    assert out["execution_authorized"] is False
