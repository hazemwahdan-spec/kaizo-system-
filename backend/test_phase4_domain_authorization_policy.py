"""Pure role-matrix tests for Phase 4 domain routes."""
from phase4_domain_authorization import _allowed_domain_roles


def test_academy_admin_writes_are_not_available_to_coaches():
    assert _allowed_domain_roles("/api/v1/academy/academies", "POST") == {"academy"}
    assert _allowed_domain_roles("/api/v1/academy/groups", "POST") == {"academy"}
    assert _allowed_domain_roles("/api/v1/academy/academies/abc/dashboard", "GET") == {"academy", "coach"}


def test_competition_write_and_read_roles_are_distinct():
    assert _allowed_domain_roles("/api/v1/competition/events", "POST") == {"academy", "coach"}
    assert _allowed_domain_roles("/api/v1/competition/events/abc", "GET") == {"academy", "coach", "athlete", "parent"}


def test_reporting_export_is_limited_to_academy_and_coach():
    assert _allowed_domain_roles("/api/v1/reporting/export", "POST") == {"academy", "coach"}
    assert _allowed_domain_roles("/api/v1/reporting/export/report-1", "GET") == {"academy", "coach"}


def test_legacy_knowledge_ingestion_is_limited_to_academy_and_coach():
    assert _allowed_domain_roles("/api/v1/knowledge/ingest", "POST") == {"academy", "coach"}


def test_unknown_domain_path_fails_closed():
    assert _allowed_domain_roles("/api/v1/unknown/write", "POST") == set()
