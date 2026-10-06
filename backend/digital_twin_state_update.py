"""FEAT-042 domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class DigitalTwinStateUpdate:
    update_id: str
    athlete_id: str
    state_version: str
    changes: str
    updated_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:DigitalTwinStateUpdate)->None:
    if not str(obj.update_id).strip(): raise ValueError("update_id is required")
    if not str(obj.athlete_id).strip(): raise ValueError("athlete_id is required")
    if not str(obj.state_version).strip(): raise ValueError("state_version is required")
    if not str(obj.changes).strip(): raise ValueError("changes is required")
    if not str(obj.updated_by).strip(): raise ValueError("updated_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:DigitalTwinStateUpdate)->dict:
    validate(obj); return {"update_id":obj.update_id,"athlete_id":obj.athlete_id,"state_version":obj.state_version,"changes":obj.changes,"updated_by":obj.updated_by,"coach_final_authority":True,"execution_authorized":False}
