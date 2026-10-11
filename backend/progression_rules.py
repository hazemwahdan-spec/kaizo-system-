"""FEAT-029 progression/regression rule engine.

Rules are advisory only. Only explicitly approved, versioned rules may be
validated for use; Coach Final Authority remains mandatory and no rule
authorizes execution automatically.
"""
from dataclasses import dataclass
import re
from typing import Literal

Operator = Literal["GT", "GTE", "LT", "LTE", "EQ"]
Action = Literal["PROGRESS", "REGRESS", "HOLD"]
RuleApprovalStatus = Literal["DRAFT", "REVIEW", "APPROVED", "RETIRED"]


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
    rule_version: str
    approval_status: RuleApprovalStatus
    coach_final_authority: bool = True
    execution_authorized: bool = False

    def matches(self, value: float) -> bool:
        return {
            "GT": value > self.threshold,
            "GTE": value >= self.threshold,
            "LT": value < self.threshold,
            "LTE": value <= self.threshold,
            "EQ": value == self.threshold,
        }[self.operator]

    def evaluate(self, value: float) -> dict:
        # Direct evaluation must not bypass version/approval governance.
        validate_rule(self)
        matched = self.matches(value)
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "approval_status": self.approval_status,
            "matched": matched,
            "action": self.action if matched else "HOLD",
            "adjustment": self.adjustment if matched else 0,
            "coach_final_authority": True,
            "execution_authorized": False,
        }


def validate_rule(rule: ProgressionRegressionRule) -> None:
    if not rule.rule_id.strip() or not rule.name.strip() or not rule.metric.strip():
        raise ValueError("rule identity and metric are required")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", rule.rule_version or ""):
        raise ValueError("rule_version must use MAJOR.MINOR.PATCH format")
    if rule.approval_status != "APPROVED":
        raise ValueError("only APPROVED rules may be evaluated")
    if not rule.coach_final_authority:
        raise ValueError("Coach Final Authority is mandatory")
    if rule.execution_authorized:
        raise ValueError("rule execution authorization must remain false")
    if rule.adjustment <= 0:
        raise ValueError("adjustment must be positive")
    if rule.operator not in {"GT", "GTE", "LT", "LTE", "EQ"}:
        raise ValueError("invalid operator")
    if rule.action not in {"PROGRESS", "REGRESS", "HOLD"}:
        raise ValueError("invalid action")
    if not rule.created_by.strip():
        raise ValueError("created_by is required")
