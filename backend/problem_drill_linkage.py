"""FEAT-032 Problem-to-Drill linkage domain model."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ProblemDrillLink:
    link_id: str
    problem_id: str
    drill_id: str
    rationale: str
    created_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate_link(link: ProblemDrillLink) -> None:
    for name, value in (("link_id", link.link_id), ("problem_id", link.problem_id), ("drill_id", link.drill_id), ("rationale", link.rationale), ("created_by", link.created_by)):
        if not str(value).strip():
            raise ValueError(f"{name} is required")
    if not link.coach_final_authority:
        raise ValueError("coach_final_authority must remain true")
    if link.execution_authorized:
        raise ValueError("execution_authorized must remain false")

def serialize_link(link: ProblemDrillLink) -> dict:
    validate_link(link)
    return {"link_id":link.link_id,"problem_id":link.problem_id,"drill_id":link.drill_id,"rationale":link.rationale,"created_by":link.created_by,"coach_final_authority":True,"execution_authorized":False}
