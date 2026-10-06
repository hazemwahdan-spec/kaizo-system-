"""FEAT-031 Drill Library domain model.

Coach-authored / evidence-aware drill objects. This module is intentionally
persistence-agnostic so the feature can be verified without changing frozen
core semantics or the existing persistence surface.
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class Drill:
    drill_id: str
    name: str
    judo_area: str
    technical_skill: str
    problem_target: str
    decision_target: str
    age_suitability: str
    skill_level: str
    execution_pattern: str
    coach_cues: Tuple[str, ...] = field(default_factory=tuple)
    common_errors: Tuple[str, ...] = field(default_factory=tuple)
    correction: str = ""
    dosage: str = ""
    intensity: str = ""
    rest: str = ""
    partner_requirement: str = ""
    equipment: str = ""
    safety_constraints: str = ""
    kpi: str = ""
    retest_link: Optional[str] = None
    competition_randori_transfer: str = ""
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    source: Tuple[str, ...] = field(default_factory=tuple)
    coach_review: bool = False
    coach_final_authority: bool = True
    execution_authorized: bool = False


def validate_drill(drill: Drill) -> None:
    required = {
        "drill_id": drill.drill_id,
        "name": drill.name,
        "judo_area": drill.judo_area,
        "technical_skill": drill.technical_skill,
        "problem_target": drill.problem_target,
        "decision_target": drill.decision_target,
        "age_suitability": drill.age_suitability,
        "skill_level": drill.skill_level,
        "execution_pattern": drill.execution_pattern,
        "kpi": drill.kpi,
        "safety_constraints": drill.safety_constraints,
    }
    missing = [key for key, value in required.items() if not str(value).strip()]
    if missing:
        raise ValueError(f"missing required drill fields: {', '.join(missing)}")

    if not drill.evidence:
        raise ValueError("at least one evidence reference is required")
    if not drill.source:
        raise ValueError("at least one source reference is required")
    if not drill.coach_final_authority:
        raise ValueError("coach_final_authority must remain true")
    if drill.execution_authorized:
        raise ValueError("execution_authorized must remain false")


def serialize_drill(drill: Drill) -> dict:
    validate_drill(drill)
    return {
        "drill_id": drill.drill_id,
        "name": drill.name,
        "judo_area": drill.judo_area,
        "technical_skill": drill.technical_skill,
        "problem_target": drill.problem_target,
        "decision_target": drill.decision_target,
        "age_suitability": drill.age_suitability,
        "skill_level": drill.skill_level,
        "execution_pattern": drill.execution_pattern,
        "coach_cues": list(drill.coach_cues),
        "common_errors": list(drill.common_errors),
        "correction": drill.correction,
        "dosage": drill.dosage,
        "intensity": drill.intensity,
        "rest": drill.rest,
        "partner_requirement": drill.partner_requirement,
        "equipment": drill.equipment,
        "safety_constraints": drill.safety_constraints,
        "kpi": drill.kpi,
        "retest_link": drill.retest_link,
        "competition_randori_transfer": drill.competition_randori_transfer,
        "evidence": list(drill.evidence),
        "source": list(drill.source),
        "coach_review": drill.coach_review,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
