"""FEAT-054 PostgreSQL integration: audit review inherits FEAT-010 scope."""
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import persistence
from productization import coach_roster, coach_audit_review


def test_review_search_is_limited_to_verified_coach_owned_athlete():
    assert persistence.is_postgres_enabled()
    persistence.initialize()
    tenant = "TENANT-" + uuid4().hex
    coach = "COACH-" + uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="FEAT-054 review"
    )
    result = coach_audit_review.review_coach_audit(
        tenant_id=tenant, coach_actor_id=coach,
        athlete_id=athlete["athlete_id"], query="COACH_ATHLETE_CREATED"
    )
    assert result is not None
    assert result["status"] == "MATCHES_FOUND"
    assert result["result_count"] == 1
    assert result["results"][0]["actor_id"] == coach
    assert result["results"][0]["actor_attribution_verified"] is True
    assert result["reviewed_by"] == coach
    assert result["read_only"] is True
    assert result["execution_authorized"] is False

    denied = coach_audit_review.review_coach_audit(
        tenant_id=tenant, coach_actor_id="OTHER-COACH",
        athlete_id=athlete["athlete_id"], query="COACH_ATHLETE_CREATED"
    )
    assert denied is None
