"""FEAT-034 Drill prescription domain model."""
from dataclasses import dataclass

@dataclass(frozen=True)
class DrillPrescription:
    prescription_id: str, drill_id: str, session_id: str, dosage: str, rationale: str, created_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate(obj: DrillPrescription) -> None:
    if not str(obj.prescription_id).strip(): raise ValueError("prescription_id is required")
    if not str(obj.drill_id).strip(): raise ValueError("drill_id is required")
    if not str(obj.session_id).strip(): raise ValueError("session_id is required")
    if not str(obj.dosage).strip(): raise ValueError("dosage is required")
    if not str(obj.rationale).strip(): raise ValueError("rationale is required")
    if not str(obj.created_by).strip(): raise ValueError("created_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")

def serialize(obj: DrillPrescription) -> dict:
    validate(obj)
    return {"prescription_id": obj.prescription_id, "drill_id": obj.drill_id, "session_id": obj.session_id, "dosage": obj.dosage, "rationale": obj.rationale, "created_by": obj.created_by, "coach_final_authority": True, "execution_authorized": False}
