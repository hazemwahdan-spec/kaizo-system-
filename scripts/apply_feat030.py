from pathlib import Path
import subprocess

root=Path(".")
main=root/"backend/main.py"
persistence=root/"backend/persistence.py"

m=main.read_text()
anchor='''@app.get("/api/v1/training-sessions/{session_id}")\ndef get_training_session(session_id: str) -> Dict[str, Any]:\n    session = persistence.get_training_session(session_id) if persistence.is_postgres_enabled() else TRAINING_SESSIONS.get(session_id)\n    if session is None:\n        raise HTTPException(status_code=404, detail="training session not found")\n    return session\n'''
addition=r'''
class TrainingSessionConstraintNoteRequest(BaseModel):
    session_id: str
    kind: str
    content: str
    priority: str = "NORMAL"
    created_by: str


@app.post("/api/v1/training-sessions/{session_id}/constraints-notes", status_code=status.HTTP_201_CREATED)
def create_training_session_constraint_note(session_id: str, req: TrainingSessionConstraintNoteRequest) -> Dict[str, Any]:
    if session_id != req.session_id:
        raise HTTPException(status_code=400, detail="session_id mismatch")
    if not req.content.strip() or not req.created_by.strip():
        raise HTTPException(status_code=400, detail="content and created_by are required")
    if req.kind.upper() not in {"CONSTRAINT", "NOTE"}:
        raise HTTPException(status_code=400, detail="kind must be CONSTRAINT or NOTE")
    if req.priority.upper() not in {"LOW", "NORMAL", "HIGH", "CRITICAL"}:
        raise HTTPException(status_code=400, detail="invalid priority")
    session = persistence.get_training_session(session_id) if persistence.is_postgres_enabled() else TRAINING_SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="training session not found")
    import uuid
    item = {
        "constraint_note_id": str(uuid.uuid4()),
        "session_id": session_id,
        "plan_id": session["plan_id"],
        "athlete_id": session["athlete_id"],
        "kind": req.kind.upper(),
        "content": req.content.strip(),
        "priority": req.priority.upper(),
        "status": "ACTIVE",
        "created_by": req.created_by.strip(),
        "created_at": datetime.utcnow().isoformat(),
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    TRAINING_SESSION_CONSTRAINT_NOTES[item["constraint_note_id"]] = item
    persistence.upsert_training_session_constraint_note(item)
    log_action(req.created_by, "TRAINING_SESSION_CONSTRAINT_NOTE_CREATED", session, item,
               "Session constraint/note recorded under coach authority; execution remains separately controlled.")
    return item


@app.get("/api/v1/training-sessions/{session_id}/constraints-notes")
def list_training_session_constraint_notes(session_id: str) -> Dict[str, Any]:
    session = persistence.get_training_session(session_id) if persistence.is_postgres_enabled() else TRAINING_SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="training session not found")
    items = (persistence.list_training_session_constraint_notes(session_id)
             if persistence.is_postgres_enabled()
             else [v for v in TRAINING_SESSION_CONSTRAINT_NOTES.values() if v["session_id"] == session_id])
    return {"session_id": session_id, "items": items, "coach_final_authority": True, "execution_authorized": False}
'''
if anchor not in m: raise SystemExit("main anchor missing")
m=m.replace(anchor,anchor+addition)
m=m.replace('TRAINING_SESSIONS: Dict[str, Dict[str, Any]] = {}','TRAINING_SESSIONS: Dict[str, Dict[str, Any]] = {}\nTRAINING_SESSION_CONSTRAINT_NOTES: Dict[str, Dict[str, Any]] = {}',1)
main.write_text(m)

p=persistence.read_text()
anchor2='''def _ensure_training_dosages_table() -> None:
'''
addition2=r'''
def _ensure_training_session_constraint_notes_table() -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_training_session_constraint_notes (
                    constraint_note_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    athlete_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        conn.commit()


def upsert_training_session_constraint_note(item: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    _ensure_training_session_constraint_notes_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kaizo_training_session_constraint_notes
                (constraint_note_id,session_id,plan_id,athlete_id,kind,content,priority,status,created_by,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (constraint_note_id) DO UPDATE SET
                  kind=EXCLUDED.kind, content=EXCLUDED.content, priority=EXCLUDED.priority,
                  status=EXCLUDED.status, created_by=EXCLUDED.created_by
            """, (item["constraint_note_id"],item["session_id"],item["plan_id"],item["athlete_id"],
                  item["kind"],item["content"],item["priority"],item["status"],item["created_by"],item["created_at"]))
        conn.commit()


def list_training_session_constraint_notes(session_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    _ensure_training_session_constraint_notes_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT constraint_note_id,session_id,plan_id,athlete_id,kind,content,priority,status,created_by,created_at
                FROM kaizo_training_session_constraint_notes
                WHERE session_id=%s ORDER BY created_at,constraint_note_id
            """, (session_id,))
            rows=cur.fetchall()
    return [{
        "constraint_note_id":r[0],"session_id":r[1],"plan_id":r[2],"athlete_id":r[3],
        "kind":r[4],"content":r[5],"priority":r[6],"status":r[7],"created_by":r[8],"created_at":r[9],
        "coach_final_authority":True,"execution_authorized":False
    } for r in rows]


'''
if anchor2 not in p: raise SystemExit("persistence anchor missing")
p=p.replace(anchor2,addition2+anchor2,1)
persistence.write_text(p)

test=Path("backend/test_feat_030_session_constraints_notes.py")
test.write_text(r'''from fastapi.testclient import TestClient
import os, uuid
os.environ["KAIZO_PERSISTENCE_MODE"]="postgres"
from backend.main import app

def test_feat_030_session_constraints_notes():
    client=TestClient(app)
    from backend import main
    plan_id="PLAN-030-"+uuid.uuid4().hex[:8]
    athlete_id="ATH-030-"+uuid.uuid4().hex[:8]
    decision_id="DEC-030-"+uuid.uuid4().hex[:8]
    main.persistence.upsert_training_plan({
        "plan_id":plan_id,"athlete_id":athlete_id,"decision_id":decision_id,
        "title":"Plan 030","objective":"Session constraints","constraints":{},
        "status":"DRAFT","created_by":"coach-030","created_at":"2026-10-06T00:00:00"
    })
    session=client.post(f"/api/v1/training-plans/{plan_id}/sessions",json={
        "plan_id":plan_id,"athlete_id":athlete_id,"title":"Session 030",
        "duration_minutes":30,"blocks":[{"name":"Main","duration_minutes":30}],"created_by":"coach-030"})
    assert session.status_code==201
    sid=session.json()["session_id"]
    created=client.post(f"/api/v1/training-sessions/{sid}/constraints-notes",json={
        "session_id":sid,"kind":"CONSTRAINT","content":"No randori above controlled intensity","priority":"HIGH","created_by":"coach-030"})
    assert created.status_code==201
    body=created.json()
    assert body["kind"]=="CONSTRAINT"
    assert body["priority"]=="HIGH"
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False
    listed=client.get(f"/api/v1/training-sessions/{sid}/constraints-notes")
    assert listed.status_code==200
    assert len(listed.json()["items"])==1
    bad=client.post(f"/api/v1/training-sessions/{sid}/constraints-notes",json={
        "session_id":sid,"kind":"BAD","content":"x","created_by":"coach-030"})
    assert bad.status_code==400
''')
wf=Path(".github/workflows/feat-030-validation.yml")
wf.write_text(r'''name: FEAT-030 Acceptance
on:
  pull_request:
    branches: [main]
    paths:
      - "backend/main.py"
      - "backend/persistence.py"
      - "backend/test_feat_030_session_constraints_notes.py"
permissions:
  contents: read
jobs:
  acceptance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - name: Install
        working-directory: backend
        run: pip install -r requirements.txt && pip install pytest
      - name: Acceptance
        working-directory: backend
        run: PYTHONPATH=.. pytest -q test_feat_030_session_constraints_notes.py
''')
subprocess.run(["git","config","user.name","github-actions[bot]"],check=True)
subprocess.run(["git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com"],check=True)
subprocess.run(["git","add","backend/main.py","backend/persistence.py","backend/test_feat_030_session_constraints_notes.py",".github/workflows/feat-030-validation.yml"],check=True)
subprocess.run(["git","commit","-m","feat(FEAT-030): session constraints and notes"],check=True)
subprocess.run(["git","push","origin","HEAD:feat-030-clean"],check=True)
