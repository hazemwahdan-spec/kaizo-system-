"""FEAT-048 knowledge lifecycle status domain model."""
from dataclasses import dataclass
@dataclass(frozen=True)
class KnowledgeLifecycleStatus:
    record_id: str
    knowledge_id: str
    status: str
    version: str
    changed_by: str
    coach_final_authority: bool=True
    execution_authorized: bool=False

def validate(obj:KnowledgeLifecycleStatus)->None:
    if not str(obj.record_id).strip(): raise ValueError("record_id is required")
    if not str(obj.knowledge_id).strip(): raise ValueError("knowledge_id is required")
    if not str(obj.status).strip(): raise ValueError("status is required")
    if not str(obj.version).strip(): raise ValueError("version is required")
    if not str(obj.changed_by).strip(): raise ValueError("changed_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")
def serialize(obj:KnowledgeLifecycleStatus)->dict:
    validate(obj); return {"record_id":obj.record_id,"knowledge_id":obj.knowledge_id,"status":obj.status,"version":obj.version,"changed_by":obj.changed_by,"coach_final_authority":True,"execution_authorized":False}
