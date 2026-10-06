"""FEAT-040 Next-decision trigger domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class NextDecisionTrigger:
    trigger_id: str
    athlete_id: str
    state_id: str
    reason: str
    triggered_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj: NextDecisionTrigger)->None:
    if not str(obj.trigger_id).strip(): raise ValueError("trigger_id is required")
    if not str(obj.athlete_id).strip(): raise ValueError("athlete_id is required")
    if not str(obj.state_id).strip(): raise ValueError("state_id is required")
    if not str(obj.reason).strip(): raise ValueError("reason is required")
    if not str(obj.triggered_by).strip(): raise ValueError("triggered_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:NextDecisionTrigger)->dict:
    validate(obj); return {"trigger_id":obj.trigger_id,"athlete_id":obj.athlete_id,"state_id":obj.state_id,"reason":obj.reason,"triggered_by":obj.triggered_by,"coach_final_authority":True,"execution_authorized":False}
