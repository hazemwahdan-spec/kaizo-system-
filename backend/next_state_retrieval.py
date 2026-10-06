"""FEAT-045 domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class NextStateRetrieval:
    retrieval_id: str
    athlete_id: str
    state_version: str
    decision_context: str
    retrieved_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:NextStateRetrieval)->None:
    if not str(obj.retrieval_id).strip(): raise ValueError("retrieval_id is required")
    if not str(obj.athlete_id).strip(): raise ValueError("athlete_id is required")
    if not str(obj.state_version).strip(): raise ValueError("state_version is required")
    if not str(obj.decision_context).strip(): raise ValueError("decision_context is required")
    if not str(obj.retrieved_by).strip(): raise ValueError("retrieved_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:NextStateRetrieval)->dict:
    validate(obj); return {"retrieval_id":obj.retrieval_id,"athlete_id":obj.athlete_id,"state_version":obj.state_version,"decision_context":obj.decision_context,"retrieved_by":obj.retrieved_by,"coach_final_authority":True,"execution_authorized":False}
