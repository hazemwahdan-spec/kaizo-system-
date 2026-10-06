"""FEAT-037 Retest capture domain model."""
from dataclasses import dataclass

@dataclass(frozen=True)
class RetestCapture:
    retest_id: str
    athlete_id: str
    kpi_values: str
    method: str
    captured_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate(obj: RetestCapture) -> None:
    if not str(obj.retest_id).strip(): raise ValueError("retest_id is required")
    if not str(obj.athlete_id).strip(): raise ValueError("athlete_id is required")
    if not str(obj.kpi_values).strip(): raise ValueError("kpi_values is required")
    if not str(obj.method).strip(): raise ValueError("method is required")
    if not str(obj.captured_by).strip(): raise ValueError("captured_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")

def serialize(obj: RetestCapture) -> dict:
    validate(obj)
    return {"retest_id": obj.retest_id, "athlete_id": obj.athlete_id, "kpi_values": obj.kpi_values, "method": obj.method, "captured_by": obj.captured_by, "coach_final_authority": True, "execution_authorized": False}
