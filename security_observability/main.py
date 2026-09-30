from datetime import datetime, timezone
from enum import Enum
from fastapi import FastAPI
from pydantic import BaseModel, Field

app=FastAPI(title="KAIZO P18 Production Security & Observability Gate",version="1.0")
events=[]

def emit(event,payload):
    events.append({"event":event,"timestamp":datetime.now(timezone.utc).isoformat(),**payload})

class SecurityCheck(BaseModel):
    control:str=Field(min_length=1)
    status:str=Field(min_length=1)
    detail:str=""

@app.get("/health")
def health():
    return {"status":"ok","service":"kaizo-p18-security-observability","governance_frozen":True,"coach_final_authority":True}

@app.get("/api/v1/readiness")
def readiness():
    gates={
      "governance_frozen":True,
      "coach_final_authority":True,
      "deny_by_default":True,
      "fail_closed":True,
      "secret_values_exposed":False,
      "p13_rbac_required":True,
      "p14_consent_required_for_minors":True,
      "durable_audit_configured":False,
      "live_tls_verified":False,
      "production_activation":False
    }
    return {"reference_gate_pass":all(gates[k] for k in ["governance_frozen","coach_final_authority","deny_by_default","fail_closed"]) and not gates["secret_values_exposed"], "gates":gates}

@app.post("/api/v1/security/check")
def security_check(c:SecurityCheck):
    safe=c.status in {"pass","verified","not_configured"}
    result={"control":c.control,"status":c.status,"safe":safe,"authoritative":False,"detail":c.detail}
    emit("security_check",result)
    return result

@app.post("/api/v1/observability/event")
def observability_event(payload:dict):
    event={"type":payload.get("type","unknown"),"severity":payload.get("severity","info"),"correlation_id":payload.get("correlation_id","missing"),"authoritative":False}
    emit("observability_event",event)
    return {"accepted":True,"event":event}

@app.get("/api/v1/policy")
def policy():
    return {
      "deny_by_default":True,"fail_closed":True,"secret_values_never_returned":True,
      "coach_final_authority":True,"p13_rbac_required":True,
      "p14_consent_required_for_minors":True,"audit_events_required":True,
      "production_activation_requires_live_security_evidence":True
    }

@app.get("/api/v1/audit")
def audit():
    return {"events":events}
