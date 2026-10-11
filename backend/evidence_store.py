"""Shared evidence lookup for Core API and governed feature contracts."""
from typing import Any, Dict, Optional

import persistence

# Memory-mode registry is shared with main.EVIDENCE_RECORDS for test/dev execution.
EVIDENCE_RECORDS: Dict[str, Dict[str, Any]] = {}


def get_evidence_record(evidence_id: str) -> Optional[Dict[str, Any]]:
    if persistence.is_postgres_enabled():
        return persistence.get_evidence(evidence_id)
    return EVIDENCE_RECORDS.get(evidence_id)
