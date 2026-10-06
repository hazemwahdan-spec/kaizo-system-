"""FEAT-038 Before/after comparison domain model."""
from dataclasses import dataclass

@dataclass(frozen=True)
class BeforeAfterComparison:
    comparison_id: str
    baseline_id: str
    retest_id: str
    findings: str
    compared_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate(obj: BeforeAfterComparison) -> None:
    if not str(obj.comparison_id).strip(): raise ValueError("comparison_id is required")
    if not str(obj.baseline_id).strip(): raise ValueError("baseline_id is required")
    if not str(obj.retest_id).strip(): raise ValueError("retest_id is required")
    if not str(obj.findings).strip(): raise ValueError("findings is required")
    if not str(obj.compared_by).strip(): raise ValueError("compared_by is required")
    if not obj.coach_final_authority: raise ValueError("coach_final_authority must remain true")
    if obj.execution_authorized: raise ValueError("execution_authorized must remain false")

def serialize(obj: BeforeAfterComparison) -> dict:
    validate(obj)
    return {"comparison_id": obj.comparison_id, "baseline_id": obj.baseline_id, "retest_id": obj.retest_id, "findings": obj.findings, "compared_by": obj.compared_by, "coach_final_authority": True, "execution_authorized": False}
