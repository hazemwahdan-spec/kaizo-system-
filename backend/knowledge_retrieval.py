"""FEAT-049 knowledge retrieval domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class KnowledgeRetrieval:
    retrieval_id: str
    knowledge_id: str
    context: str
    retrieved_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:KnowledgeRetrieval)->None:
    if not str(obj.retrieval_id).strip(): raise ValueError("retrieval_id is required")
    if not str(obj.knowledge_id).strip(): raise ValueError("knowledge_id is required")
    if not str(obj.context).strip(): raise ValueError("context is required")
    if not str(obj.retrieved_by).strip(): raise ValueError("retrieved_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:KnowledgeRetrieval)->dict:
    validate(obj); return {"retrieval_id":obj.retrieval_id,"knowledge_id":obj.knowledge_id,"context":obj.context,"retrieved_by":obj.retrieved_by,"coach_final_authority":True,"execution_authorized":False}
