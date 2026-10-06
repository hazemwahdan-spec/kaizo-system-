"""FEAT-047 source provenance linkage domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class SourceProvenanceLinkage:
    link_id: str
    knowledge_id: str
    source_id: str
    source_type: str
    citation: str
    linked_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:SourceProvenanceLinkage)->None:
    if not str(obj.link_id).strip(): raise ValueError("link_id is required")
    if not str(obj.knowledge_id).strip(): raise ValueError("knowledge_id is required")
    if not str(obj.source_id).strip(): raise ValueError("source_id is required")
    if not str(obj.source_type).strip(): raise ValueError("source_type is required")
    if not str(obj.citation).strip(): raise ValueError("citation is required")
    if not str(obj.linked_by).strip(): raise ValueError("linked_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:SourceProvenanceLinkage)->dict:
    validate(obj); return {"link_id":obj.link_id,"knowledge_id":obj.knowledge_id,"source_id":obj.source_id,"source_type":obj.source_type,"citation":obj.citation,"linked_by":obj.linked_by,"coach_final_authority":True,"execution_authorized":False}
