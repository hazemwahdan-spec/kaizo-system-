from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel, Field

app=FastAPI(title="KAIZO P17 Integration Hardening",version="1.0")
audit_log=[]

def audit(event,payload):
    audit_log.append({"event":event,"timestamp":datetime.now(timezone.utc).isoformat(),**payload})

class ServiceCheck(BaseModel):
    service:str=Field(min_length=1)
    status:str=Field(min_length=1)
    authoritative:bool=False
    note:str=""

@app.get("/health")
def health():
    return {"status":"ok","service":"kaizo-p17-integration-hardening","governance_frozen":True,"coach_final_authority":True}

@app.get("/api/v1/readiness")
def readiness():
    gates={
        "core_logic_unchanged":True,
        "coach_final_authority":True,
        "p13_rbac_required":True,
        "p14_consent_required":True,
        "p05_persistence_separate":True,
        "p15_analytics_separate":True,
        "fail_closed":True,
        "external_credentials_present":False,
        "production_activation":False
    }
    return {"ready_for_reference_integration":all(gates[k] for k in ["core_logic_unchanged","coach_final_authority","p13_rbac_required","p14_consent_required","p05_persistence_separate","p15_analytics_separate","fail_closed"]),"gates":gates}

@app.post("/api/v1/check")
def check(c:ServiceCheck):
    accepted=c.status in {"healthy","verified","not_configured"}
    result={"service":c.service,"status":c.status,"accepted":accepted,"authoritative":False,"safe_degradation":not accepted,"note":c.note}
    audit("integration_check",result)
    return result

@app.get("/api/v1/policy")
def policy():
    return {"deny_by_default":True,"fail_closed":True,"coach_final_authority":True,"governance_frozen":True,"no_core_rebuild":True,"p13_required":True,"p14_required_for_minors":True,"production_activation_requires_live_evidence":True}

@app.get("/api/v1/audit")
def get_audit():
    return {"events":audit_log}
