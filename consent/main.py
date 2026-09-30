from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="KAIZO P14 Minor/Child Consent Layer", version="1.0")

class ConsentState(str, Enum):
    pending = "pending"
    active = "active"
    revoked = "revoked"
    expired = "expired"

class Consent(BaseModel):
    child_id: str
    guardian_id: str
    academy_id: str
    resource: str
    action: str
    state: ConsentState
    expires_at: Optional[str] = None

class AccessRequest(BaseModel):
    child_id: str
    guardian_id: str
    academy_id: str
    resource: str
    action: str

class ConsentChange(BaseModel):
    consent: Consent
    actor_id: str = Field(min_length=1)

CONSENTS: list[Consent] = []
AUDIT: list[dict] = []

def audit(event: str, payload: dict):
    AUDIT.append({"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), **payload})

def valid(c: Consent, r: AccessRequest) -> tuple[bool, str]:
    if c.child_id != r.child_id: return False, "child_mismatch"
    if c.guardian_id != r.guardian_id: return False, "guardian_mismatch"
    if c.academy_id != r.academy_id: return False, "academy_mismatch"
    if c.resource != r.resource or c.action != r.action: return False, "scope_mismatch"
    if c.state != ConsentState.active: return False, f"consent_{c.state.value}"
    if c.expires_at:
        try:
            if datetime.fromisoformat(c.expires_at.replace("Z","+00:00")) <= datetime.now(timezone.utc):
                return False, "consent_expired"
        except ValueError:
            return False, "invalid_expiry"
    return True, "active_consent"

@app.get("/health")
def health():
    return {"status":"ok", "service":"kaizo-p14-consent", "deny_by_default":True, "p13_separate":True}

@app.post("/api/v1/consents")
def upsert_consent(change: ConsentChange):
    global CONSENTS
    CONSENTS = [c for c in CONSENTS if not (c.child_id == change.consent.child_id and c.guardian_id == change.consent.guardian_id and c.academy_id == change.consent.academy_id and c.resource == change.consent.resource and c.action == change.consent.action)]
    CONSENTS.append(change.consent)
    audit("consent_change", {"actor_id":change.actor_id,"child_id":change.consent.child_id,"guardian_id":change.consent.guardian_id,"academy_id":change.consent.academy_id,"resource":change.consent.resource,"action":change.consent.action,"state":change.consent.state.value})
    return {"stored":True,"state":change.consent.state.value}

@app.post("/api/v1/authorize-child-data")
def authorize(req: AccessRequest):
    matches = [c for c in CONSENTS if c.child_id == req.child_id and c.guardian_id == req.guardian_id and c.academy_id == req.academy_id and c.resource == req.resource and c.action == req.action]
    if not matches:
        allowed, reason = False, "no_consent"
    else:
        allowed, reason = valid(matches[-1], req)
    audit("child_data_authorization", {"child_id":req.child_id,"guardian_id":req.guardian_id,"academy_id":req.academy_id,"resource":req.resource,"action":req.action,"allowed":allowed,"reason":reason})
    return {"allowed":allowed,"reason":reason,"coach_final_authority":True,"p13_rbac_required":True}

@app.get("/api/v1/audit")
def audit_log():
    return {"events":AUDIT}

@app.get("/api/v1/policy")
def policy():
    return {"deny_by_default":True,"consent_is_scope_specific":True,"guardian_role_alone_is_insufficient":True,"p13_rbac_separate":True,"p05_persistence_separate":True}
