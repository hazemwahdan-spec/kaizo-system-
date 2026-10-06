"""FEAT-050 reusable knowledge linkage domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class ReusableKnowledgeLinkage:
    link_id: str
    knowledge_id: str
    capability: str
    linked_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:ReusableKnowledgeLinkage)->None:
    if not str(obj.link_id).strip(): raise ValueError("link_id is required")
    if not str(obj.knowledge_id).strip(): raise ValueError("knowledge_id is required")
    if not str(obj.capability).strip(): raise ValueError("capability is required")
    if not str(obj.linked_by).strip(): raise ValueError("linked_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:ReusableKnowledgeLinkage)->dict:
    validate(obj); return {"link_id":obj.link_id,"knowledge_id":obj.knowledge_id,"capability":obj.capability,"linked_by":obj.linked_by,"coach_final_authority":True,"execution_authorized":False}
