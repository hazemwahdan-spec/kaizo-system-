from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app=FastAPI(title="KAIZO RBAC Reference Service",version="1.0")

ROLE_PERMISSIONS={
"coach":{"athlete:read","athlete:write","session:write","decision:execute"},
"technical_director":{"athlete:read","athlete:write","session:write","decision:execute","technical:manage"},
"academy_director":{"academy:read","academy:manage","athlete:read","athlete:write","session:write","decision:execute","technical:manage","rbac:manage"},
"academy_admin":{"academy:read","athlete:read","session:read","rbac:manage"},
"athlete":{"self:read","self:write"},
"parent_guardian":{"guardian:self:read","guardian:self:write"},
"researcher":{"research:read","research:write"},
"system":{"system:execute","audit:write"},
}
VALID_ROLES=set(ROLE_PERMISSIONS)

class AuthorizationRequest(BaseModel):
    role:str
    action:str
    resource_academy_id:str
    actor_academy_id:str

AUDIT=[]

def authorize(req:AuthorizationRequest):
    allowed=req.role in VALID_ROLES and req.actor_academy_id==req.resource_academy_id and req.action in ROLE_PERMISSIONS.get(req.role,set())
    event={"timestamp":datetime.now(timezone.utc).isoformat(),"role":req.role,"action":req.action,"resource_academy_id":req.resource_academy_id,"actor_academy_id":req.actor_academy_id,"allowed":allowed}
    AUDIT.append(event)
    return allowed,event

@app.get("/health")
def health(): return {"status":"ok","service":"kaizo-rbac","policy":"deny-by-default"}

@app.get("/api/v1/roles")
def roles(): return {"roles":sorted(VALID_ROLES),"permission_matrix":{k:sorted(v) for k,v in ROLE_PERMISSIONS.items()}}

@app.post("/api/v1/authorize")
def check(req:AuthorizationRequest):
    allowed,event=authorize(req)
    if not allowed:
        raise HTTPException(status_code=403,detail={"authorized":False,"audit_event":event})
    return {"authorized":True,"audit_event":event}

@app.get("/api/v1/audit")
def audit(): return {"events":AUDIT}

@app.get("/api/v1/policy")
def policy():
    return {"deny_by_default":True,"academy_scope_enforced":True,"client_checks_non_authoritative":True,"p14_minor_consent_required_separately":True,"coach_final_authority":True}