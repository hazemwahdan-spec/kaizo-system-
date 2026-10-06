"""FEAT-033 Decision-to-drill selection domain model."""
from dataclasses import dataclass

@dataclass(frozen=True)
class DecisionDrillSelection:
    decision_id: str, drill_id: str, rationale: str, selected_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate(obj: DecisionDrillSelection) -> None:
    if not str(obj.decision_id).strip(): raise ValueError("decision_id is required")
    if not str(obj.drill_id).strip(): raise ValueError("drill_id is required")
    if not str(obj.rationale).strip(): raise ValueError("rationale is required")
    if not str(obj.selected_by).strip(): raise ValueError("selected_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")

def serialize(obj: DecisionDrillSelection) -> dict:
    validate(obj)
    return {"decision_id": obj.decision_id, "drill_id": obj.drill_id, "rationale": obj.rationale, "selected_by": obj.selected_by, "coach_final_authority": True, "execution_authorized": False}
