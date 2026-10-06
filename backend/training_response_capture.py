"""FEAT-036 Training response capture domain model."""
from dataclasses import dataclass

@dataclass(frozen=True)
class TrainingResponse:
    response_id: str
    session_id: str
    athlete_id: str
    response: str
    kpi_values: str
    captured_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate(obj: TrainingResponse) -> None:
    if not str(obj.response_id).strip(): raise ValueError("response_id is required")
    if not str(obj.session_id).strip(): raise ValueError("session_id is required")
    if not str(obj.athlete_id).strip(): raise ValueError("athlete_id is required")
    if not str(obj.response).strip(): raise ValueError("response is required")
    if not str(obj.kpi_values).strip(): raise ValueError("kpi_values is required")
    if not str(obj.captured_by).strip(): raise ValueError("captured_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")

def serialize(obj: TrainingResponse) -> dict:
    validate(obj)
    return {"response_id": obj.response_id, "session_id": obj.session_id, "athlete_id": obj.athlete_id, "response": obj.response, "kpi_values": obj.kpi_values, "captured_by": obj.captured_by, "coach_final_authority": True, "execution_authorized": False}
