"""FEAT-046 governed knowledge record domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class GovernedKnowledgeRecord:
    knowledge_id: str
    topic: str
    claim: str
    evidence_level: str
    status: str
    created_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:GovernedKnowledgeRecord)->None:
    if not str(obj.knowledge_id).strip(): raise ValueError("knowledge_id is required")
    if not str(obj.topic).strip(): raise ValueError("topic is required")
    if not str(obj.claim).strip(): raise ValueError("claim is required")
    if not str(obj.evidence_level).strip(): raise ValueError("evidence_level is required")
    if not str(obj.status).strip(): raise ValueError("status is required")
    if not str(obj.created_by).strip(): raise ValueError("created_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:GovernedKnowledgeRecord)->dict:
    validate(obj); return {"knowledge_id":obj.knowledge_id,"topic":obj.topic,"claim":obj.claim,"evidence_level":obj.evidence_level,"status":obj.status,"created_by":obj.created_by,"coach_final_authority":True,"execution_authorized":False}
