"""FEAT-043 domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class StateVersionHistory:
    history_id: str
    athlete_id: str
    state_version: str
    snapshot: str
    recorded_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:StateVersionHistory)->None:
    if not str(obj.history_id).strip(): raise ValueError("history_id is required")
    if not str(obj.athlete_id).strip(): raise ValueError("athlete_id is required")
    if not str(obj.state_version).strip(): raise ValueError("state_version is required")
    if not str(obj.snapshot).strip(): raise ValueError("snapshot is required")
    if not str(obj.recorded_by).strip(): raise ValueError("recorded_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:StateVersionHistory)->dict:
    validate(obj); return {"history_id":obj.history_id,"athlete_id":obj.athlete_id,"state_version":obj.state_version,"snapshot":obj.snapshot,"recorded_by":obj.recorded_by,"coach_final_authority":True,"execution_authorized":False}
