"""FEAT-039 Progress state update domain model."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ProgressStateUpdate:
    state_id: str
    athlete_id: str
    comparison_id: str
    progress_state: str
    updated_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate(obj: ProgressStateUpdate) -> None:
    if not str(obj.state_id).strip(): raise ValueError("state_id is required")
    if not str(obj.athlete_id).strip(): raise ValueError("athlete_id is required")
    if not str(obj.comparison_id).strip(): raise ValueError("comparison_id is required")
    if not str(obj.progress_state).strip(): raise ValueError("progress_state is required")
    if not str(obj.updated_by).strip(): raise ValueError("updated_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")

def serialize(obj: ProgressStateUpdate) -> dict:
    validate(obj)
    return {"state_id": obj.state_id, "athlete_id": obj.athlete_id, "comparison_id": obj.comparison_id, "progress_state": obj.progress_state, "updated_by": obj.updated_by, "coach_final_authority": True, "execution_authorized": False}
