from datetime import datetime, timezone
from collections import defaultdict
from fastapi import FastAPI
from pydantic import BaseModel, Field

app=FastAPI(title="KAIZO P15 Scalable Analytics Infrastructure",version="1.0")
EVENTS=[]
AUDIT=[]

class Event(BaseModel):
    event_id:str=Field(min_length=1)
    academy_id:str=Field(min_length=1)
    athlete_id:str=Field(min_length=1)
    metric:str=Field(min_length=1)
    value:float
    unit:str=Field(min_length=1)
    observed_at:str
    source:str=Field(min_length=1)
    quality:str="unverified"

def audit(event,payload): AUDIT.append({"event":event,"timestamp":datetime.now(timezone.utc).isoformat(),**payload})

@app.get("/health")
def health(): return {"status":"ok","service":"kaizo-p15-analytics","descriptive_only":True,"p05_separate":True,"p13_rbac_required":True,"p14_consent_required":True}

@app.post("/api/v1/events")
def ingest(e:Event):
    if any(x["event_id"]==e.event_id for x in EVENTS): return {"stored":False,"reason":"duplicate_event_id"}
    EVENTS.append(e.model_dump()); audit("analytics_event_ingest",{"event_id":e.event_id,"academy_id":e.academy_id,"athlete_id":e.athlete_id,"metric":e.metric,"source":e.source,"quality":e.quality}); return {"stored":True,"event_id":e.event_id}

@app.get("/api/v1/summary/{athlete_id}")
def summary(athlete_id:str):
    rows=[x for x in EVENTS if x["athlete_id"]==athlete_id]
    groups=defaultdict(list)
    for x in rows: groups[(x["academy_id"],x["metric"],x["unit"])].append(x["value"])
    out=[]
    for (academy,metric,unit),vals in groups.items(): out.append({"academy_id":academy,"athlete_id":athlete_id,"metric":metric,"unit":unit,"count":len(vals),"min":min(vals),"max":max(vals),"mean":sum(vals)/len(vals),"descriptive":True})
    audit("analytics_summary_read",{"athlete_id":athlete_id,"groups":len(out)}); return {"athlete_id":athlete_id,"summaries":out,"scientific_validation_not_implied":True,"predictive_ranking":False}

@app.get("/api/v1/events")
def events(): return {"events":EVENTS,"authoritative":False,"note":"Reference runtime only"}

@app.get("/api/v1/audit")
def audit_log(): return {"events":AUDIT}

@app.get("/api/v1/policy")
def policy(): return {"descriptive_only":True,"no_predictive_ranking":True,"no_medical_inference":True,"p05_separate":True,"p13_rbac_required":True,"p14_consent_required":True,"coach_final_authority":True,"provenance_required":True}
