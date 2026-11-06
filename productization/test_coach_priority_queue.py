import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from productization.coach_priority_queue import build_priority_items


def test_queue_uses_only_explicit_trigger_and_unmatched_response_evidence():
    athletes = [{"athlete_id":"A1","display_name":"Owned"}]
    records = [
        {"record_id":"resp-1","feature_id":"FEAT-036","athlete_id":"A1",
         "session_id":"S1","payload":{"response":{"kpi":"grip"}}, "created_at":"2026-11-01"},
        {"record_id":"retest-1","feature_id":"FEAT-037","athlete_id":"A1",
         "session_id":"S2","payload":{"retest_values":{"grip":2}}, "created_at":"2026-11-02"},
        {"record_id":"trigger-1","feature_id":"FEAT-040","athlete_id":"A1",
         "session_id":"S3","payload":{"trigger_reason":"Retest changed baseline",
         "required_evidence":["EV-1"]}, "created_at":"2026-11-03"},
        {"record_id":"foreign","feature_id":"FEAT-040","athlete_id":"OTHER",
         "payload":{"trigger_reason":"foreign","required_evidence":["EV-X"]}},
    ]
    items = build_priority_items(athletes, records)
    assert [x["item_id"] for x in items] == ["trigger-1", "resp-1"]
    assert items[0]["evidence_refs"] == ["EV-1"]
    assert items[1]["item_type"] == "RESPONSE_WITHOUT_RETEST"
    assert all(x["priority_rank"] is None and x["due_at"] is None for x in items)
    assert all(x["review_state"] == "STATUS_NOT_TRACKED" for x in items)


def test_queue_does_not_create_items_without_required_evidence():
    athletes = [{"athlete_id":"A1","display_name":"Owned"}]
    records = [
        {"record_id":"bad-trigger","feature_id":"FEAT-040","athlete_id":"A1",
         "payload":{"trigger_reason":"No required evidence","required_evidence":[]}},
        {"record_id":"paired-response","feature_id":"FEAT-036","athlete_id":"A1",
         "session_id":"S1","payload":{}},
        {"record_id":"paired-retest","feature_id":"FEAT-037","athlete_id":"A1",
         "session_id":"S1","payload":{}},
    ]
    assert build_priority_items(athletes, records) == []
