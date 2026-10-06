"""FEAT-044 domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class DecisionCycleStateLinkage:
    link_id: str
    decision_id: str
    athlete_id: str
    state_version: str
    linked_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:DecisionCycleStateLinkage)->None:
    if not str(obj.link_id).strip(): raise ValueError("link_id is required")
    if not str(obj.decision_id).strip(): raise ValueError("decision_id is required")
    if not str(obj.athlete_id).strip(): raise ValueError("athlete_id is required")
    if not str(obj.state_version).strip(): raise ValueError("state_version is required")
    if not str(obj.linked_by).strip(): raise ValueError("linked_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:DecisionCycleStateLinkage)->dict:
    validate(obj); return {"link_id":obj.link_id,"decision_id":obj.decision_id,"athlete_id":obj.athlete_id,"state_version":obj.state_version,"linked_by":obj.linked_by,"coach_final_authority":True,"execution_authorized":False}
