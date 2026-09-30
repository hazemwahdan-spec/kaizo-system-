import os, json, uuid
from datetime import datetime, timezone
from typing import Any, Optional
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv("DATABASE_URL")
app = FastAPI(title="KAIZO Longitudinal Athlete Record", version="1.0")

SCHEMA = """
CREATE TABLE IF NOT EXISTS athletes (
 id uuid PRIMARY KEY,
 academy_id text NOT NULL,
 display_name text NOT NULL,
 birth_year int,
 is_minor boolean NOT NULL DEFAULT true,
 consent_status text NOT NULL DEFAULT 'required',
 status text NOT NULL DEFAULT 'active',
 created_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS athlete_events (
 id uuid PRIMARY KEY,
 athlete_id uuid NOT NULL REFERENCES athletes(id),
 academy_id text NOT NULL,
 event_type text NOT NULL,
 occurred_at timestamptz NOT NULL,
 actor_role text NOT NULL,
 source_ref text,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
 id uuid PRIMARY KEY,
 academy_id text NOT NULL,
 athlete_id uuid,
 action text NOT NULL,
 actor_role text NOT NULL,
 occurred_at timestamptz NOT NULL,
 metadata jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_athlete_time ON athlete_events(athlete_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_academy_time ON athlete_events(academy_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_athlete_time ON audit_log(athlete_id, occurred_at);
"""

def now():
    return datetime.now(timezone.utc)

def db():
    if not DATABASE_URL:
        raise HTTPException(503, "P05_PERSISTENCE_UNAVAILABLE")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

@app.on_event("startup")
def startup():
    if DATABASE_URL:
        with db() as c:
            c.execute(SCHEMA)
            c.commit()

def guard(actor_role: Optional[str], academy_id: Optional[str]):
    if not actor_role or not academy_id:
        raise HTTPException(403, "GOVERNANCE_CONTEXT_REQUIRED")
    allowed = {"coach","technical_director","academy_director","system"}
    if actor_role not in allowed:
        raise HTTPException(403, "ACTOR_ROLE_NOT_ALLOWED")

def audit(c, academy_id, athlete_id, action, actor_role, metadata):
    c.execute(
        "INSERT INTO audit_log VALUES (%s,%s,%s,%s,%s,%s)",
        (uuid.uuid4(), academy_id, athlete_id, action, actor_role, now(), json.dumps(metadata))
    )

def get_athlete(c, athlete_id, academy_id):
    row = c.execute("SELECT * FROM athletes WHERE id=%s AND academy_id=%s", (athlete_id, academy_id)).fetchone()
    if not row:
        raise HTTPException(404, "ATHLETE_NOT_FOUND")
    if row["is_minor"] and row["consent_status"] != "active":
        raise HTTPException(403, "MINOR_CONSENT_REQUIRED")
    return row

class AthleteIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    birth_year: Optional[int] = None
    is_minor: bool = True
    consent_status: str = "required"

class EventIn(BaseModel):
    event_type: str = Field(min_length=2, max_length=80)
    occurred_at: Optional[datetime] = None
    payload: dict[str, Any] = {}
    source_ref: Optional[str] = None

@app.get("/health")
def health():
    if not DATABASE_URL:
        return {"status":"HOLD","persistence":"missing"}
    try:
        with db() as c:
            c.execute("SELECT 1")
        return {"status":"OK","persistence":"postgresql","governance":"P05"}
    except Exception:
        return {"status":"HOLD","persistence":"unavailable"}

@app.post("/api/v1/athletes")
def create_athlete(body: AthleteIn, x_kaizo_actor_role: Optional[str]=Header(None), x_kaizo_academy_id: Optional[str]=Header(None)):
    guard(x_kaizo_actor_role, x_kaizo_academy_id)
    consent = body.consent_status if (not body.is_minor or body.consent_status == "active") else "required"
    athlete_id = uuid.uuid4()
    t = now()
    with db() as c:
        c.execute("INSERT INTO athletes VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                  (athlete_id,x_kaizo_academy_id,body.display_name,body.birth_year,body.is_minor,consent,"active",t,t))
        audit(c,x_kaizo_academy_id,athlete_id,"ATHLETE_CREATED",x_kaizo_actor_role,{"minor":body.is_minor,"consent":consent})
        c.commit()
    return {"athlete_id":str(athlete_id),"consent_status":consent,"access":"blocked" if body.is_minor and consent!="active" else "allowed"}

@app.post("/api/v1/athletes/{athlete_id}/events")
def append_event(athlete_id: str, body: EventIn, x_kaizo_actor_role: Optional[str]=Header(None), x_kaizo_academy_id: Optional[str]=Header(None)):
    guard(x_kaizo_actor_role, x_kaizo_academy_id)
    try: aid = uuid.UUID(athlete_id)
    except ValueError: raise HTTPException(400,"INVALID_ATHLETE_ID")
    with db() as c:
        get_athlete(c, aid, x_kaizo_academy_id)
        event_id=uuid.uuid4(); occurred=body.occurred_at or now()
        c.execute("INSERT INTO athlete_events VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  (event_id,aid,x_kaizo_academy_id,body.event_type,occurred,x_kaizo_actor_role,body.source_ref,json.dumps(body.payload),now()))
        audit(c,x_kaizo_academy_id,aid,"EVENT_APPENDED",x_kaizo_actor_role,{"event_id":str(event_id),"event_type":body.event_type})
        c.commit()
    return {"event_id":str(event_id),"status":"persisted"}

@app.get("/api/v1/athletes/{athlete_id}/timeline")
def timeline(athlete_id: str, x_kaizo_actor_role: Optional[str]=Header(None), x_kaizo_academy_id: Optional[str]=Header(None)):
    guard(x_kaizo_actor_role, x_kaizo_academy_id)
    try: aid=uuid.UUID(athlete_id)
    except ValueError: raise HTTPException(400,"INVALID_ATHLETE_ID")
    with db() as c:
        athlete=get_athlete(c,aid,x_kaizo_academy_id)
        events=c.execute("""SELECT id,event_type,occurred_at,actor_role,source_ref,payload
                            FROM athlete_events WHERE athlete_id=%s AND academy_id=%s
                            ORDER BY occurred_at ASC, created_at ASC""",(aid,x_kaizo_academy_id)).fetchall()
        return {"athlete":dict(athlete),"events":[dict(e) for e in events]}

@app.get("/api/v1/athletes/{athlete_id}/summary")
def summary(athlete_id: str, x_kaizo_actor_role: Optional[str]=Header(None), x_kaizo_academy_id: Optional[str]=Header(None)):
    guard(x_kaizo_actor_role, x_kaizo_academy_id)
    try: aid=uuid.UUID(athlete_id)
    except ValueError: raise HTTPException(400,"INVALID_ATHLETE_ID")
    with db() as c:
        get_athlete(c,aid,x_kaizo_academy_id)
        counts=c.execute("""SELECT event_type,count(*) AS count
                            FROM athlete_events WHERE athlete_id=%s GROUP BY event_type ORDER BY event_type""",(aid,)).fetchall()
        last=c.execute("""SELECT event_type,occurred_at FROM athlete_events
                          WHERE athlete_id=%s ORDER BY occurred_at DESC,created_at DESC LIMIT 1""",(aid,)).fetchone()
        return {"athlete_id":str(aid),"event_counts":[dict(x) for x in counts],"last_event":dict(last) if last else None,
                "coach_final_authority":True,"scientific_validation_not_implied":True}

@app.get("/api/v1/athletes/{athlete_id}/audit")
def audit_read(athlete_id: str, x_kaizo_actor_role: Optional[str]=Header(None), x_kaizo_academy_id: Optional[str]=Header(None)):
    guard(x_kaizo_actor_role, x_kaizo_academy_id)
    try: aid=uuid.UUID(athlete_id)
    except ValueError: raise HTTPException(400,"INVALID_ATHLETE_ID")
    with db() as c:
        get_athlete(c,aid,x_kaizo_academy_id)
        rows=c.execute("""SELECT action,actor_role,occurred_at,metadata FROM audit_log
                          WHERE athlete_id=%s AND academy_id=%s ORDER BY occurred_at ASC""",(aid,x_kaizo_academy_id)).fetchall()
        return {"audit":[dict(x) for x in rows]}

@app.get("/api/v1/record-contract")
def record_contract():
    return {
      "version":"1.0",
      "event_types":["training","assessment","goal","observation","decision","intervention","kpi_measurement","retest","competition","self_reflection","milestone"],
      "immutability":"append-only event history; corrections are new events",
      "authority":"Coach Final Authority",
      "minor_gate":"P14 consent required before access to minor records",
      "identity_gate":"P13 production authentication/RBAC remains separate",
      "analytics_gate":"P15 scalable analytics remains separate"
    }
