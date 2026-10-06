"""FEAT-030: session constraints and notes domain model.

This layer defines the validated record used by the session feature.
Persistence/API wiring remains outside this module until the repository
editing path can update the existing large core files safely.
"""
from dataclasses import dataclass
from typing import Literal

Kind = Literal["CONSTRAINT", "NOTE"]
Priority = Literal["LOW", "NORMAL", "HIGH", "CRITICAL"]

@dataclass(frozen=True)
class SessionConstraintNote:
    item_id: str
    session_id: str
    kind: Kind
    content: str
    priority: Priority
    created_by: str
    coach_final_authority: bool = True
    execution_authorized: bool = False

def validate_item(item: SessionConstraintNote) -> None:
    if not item.item_id.strip() or not item.session_id.strip():
        raise ValueError("item_id and session_id are required")
    if not item.content.strip() or not item.created_by.strip():
        raise ValueError("content and created_by are required")
    if item.kind not in {"CONSTRAINT", "NOTE"}:
        raise ValueError("kind must be CONSTRAINT or NOTE")
    if item.priority not in {"LOW", "NORMAL", "HIGH", "CRITICAL"}:
        raise ValueError("invalid priority")

def serialize_item(item: SessionConstraintNote) -> dict:
    validate_item(item)
    return {
        "item_id": item.item_id,
        "session_id": item.session_id,
        "kind": item.kind,
        "content": item.content.strip(),
        "priority": item.priority,
        "created_by": item.created_by.strip(),
        "coach_final_authority": True,
        "execution_authorized": False,
    }
