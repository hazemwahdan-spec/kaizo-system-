"""FEAT-029 progression/regression rule engine.

Rules are advisory only. Coach Final Authority remains mandatory and no rule
authorizes execution automatically.
"""
from dataclasses import dataclass
from typing import Literal

Operator = Literal["GT", "GTE", "LT", "LTE", "EQ"]
Action = Literal["PROGRESS", "REGRESS", "HOLD"]

@dataclass(frozen=True)
class ProgressionRegressionRule:
    rule_id: str
    name: str
    metric: str
    operator: Operator
    threshold: float
    action: Action
    adjustment: float
    created_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

    def matches(self, value: float) -> bool:
        return {"GT": value > self.threshold, "GTE": value >= self.threshold,
                "LT": value < self.threshold, "LTE": value <= self.threshold,
                "EQ": value == self.threshold}[self.operator]

    def evaluate(self, value: float) -> dict:
        matched = self.matches(value)
        return {"rule_id": self.rule_id, "matched": matched,
                "action": self.action if matched else "HOLD",
                "adjustment": self.adjustment if matched else 0,
                "coach_final_authority": True, "execution_authorized": False}

def validate_rule(rule: ProgressionRegressionRule) -> None:
    if not rule.rule_id.strip() or not rule.name.strip() or not rule.metric.strip():
        raise ValueError("rule identity and metric are required")
    if rule.adjustment <= 0:
        raise ValueError("adjustment must be positive")
    if rule.operator not in {"GT", "GTE", "LT", "LTE", "EQ"}:
        raise ValueError("invalid operator")
    if rule.action not in {"PROGRESS", "REGRESS", "HOLD"}:
        raise ValueError("invalid action")
    if not rule.created_by.strip():
        raise ValueError("created_by is required")
