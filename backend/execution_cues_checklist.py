"""FEAT-035 domain model."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionCueChecklist:
    checklist_id: str
    prescription_id: str
    cues: str
    checks: str
    created_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate(obj: ExecutionCueChecklist) -> None:
    if not str(obj.checklist_id).strip(): raise ValueError("checklist_id is required")
    if not str(obj.prescription_id).strip(): raise ValueError("prescription_id is required")
    if not str(obj.cues).strip(): raise ValueError("cues is required")
    if not str(obj.checks).strip(): raise ValueError("checks is required")
    if not str(obj.created_by).strip(): raise ValueError("created_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")

def serialize(obj: ExecutionCueChecklist) -> dict:
    validate(obj)
    return {"checklist_id": obj.checklist_id, "prescription_id": obj.prescription_id, "cues": obj.cues, "checks": obj.checks, "created_by": obj.created_by, "coach_final_authority": True, "execution_authorized": False}
