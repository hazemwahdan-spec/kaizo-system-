from fastapi import FastAPI
from pydantic import BaseModel, Field

app=FastAPI(title="KAIZO P20 E2E Acceptance Gate",version="1.0")

REQUIRED=["governance","core","coach_ui","technical","academy","athlete","training","analytics","video","wearables","competition","education","research","rbac","consent","analytics_infra","ai_assistance","integration_hardening","security_observability","production_evidence"]

class AcceptanceInput(BaseModel):
    evidence:dict[str,bool]=Field(default_factory=dict)
    live_production:bool=False

@app.get("/health")
def health():
    return {"status":"ok","service":"kaizo-p20-e2e-acceptance","coach_final_authority":True,"acceptance_claim":False}

@app.get("/api/v1/matrix")
def matrix():
    return {"required":REQUIRED,"count":len(REQUIRED)}

@app.post("/api/v1/evaluate")
def evaluate(i:AcceptanceInput):
    missing=[k for k in REQUIRED if not i.evidence.get(k,False)]
    reference_complete=len(missing)==0
    production_acceptance=reference_complete and i.live_production
    return {"reference_complete":reference_complete,"production_acceptance_verified":production_acceptance,"missing":missing,"coach_final_authority":True,"authoritative":False}

@app.get("/api/v1/policy")
def policy():
    return {"evidence_before_claim":True,"live_production_required_for_acceptance":True,"coach_final_authority":True,"core_rebuild":False,"autonomous_decision":False}

