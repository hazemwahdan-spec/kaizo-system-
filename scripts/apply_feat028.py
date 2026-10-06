from pathlib import Path

root = Path(__file__).resolve().parents[1]

main = root / "backend" / "main.py"
text = main.read_text()
marker = "\n\nclass CauseContextFramingRequest(BaseModel):"
feature = r'''
class TrainingDosageRequest(BaseModel):
    session_id: str
    block_name: str
    sets: int
    reps: int
    rest_seconds: int = 0
    dosage_notes: Optional[str] = None
    prescribed_by: str


TRAINING_DOSAGES: Dict[str, Dict[str, Any]] = {}


@app.post("/api/v1/training-sessions/{session_id}/dosage", status_code=status.HTTP_201_CREATED)
def create_training_dosage(session_id: str, req: TrainingDosageRequest) -> Dict[str, Any]:
    if session_id != req.session_id:
        raise HTTPException(status_code=400, detail="session_id mismatch")
    if not req.block_name.strip() or not req.prescribed_by.strip():
        raise HTTPException(status_code=400, detail="block_name and prescribed_by are required")
    if req.sets <= 0 or req.reps <= 0 or req.rest_seconds < 0:
        raise HTTPException(status_code=400, detail="sets and reps must be positive and rest_seconds cannot be negative")

    session = (
        persistence.get_training_session(session_id)
        if persistence.is_postgres_enabled()
        else TRAINING_SESSIONS.get(session_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="training session not found")

    block_names = {str(block.get("name", "")).strip() for block in session.get("blocks", [])}
    if req.block_name.strip() not in block_names:
        raise HTTPException(status_code=400, detail="block_name must match an existing session block")

    import uuid
    now = datetime.utcnow().isoformat()
    dosage = {
        "dosage_id": str(uuid.uuid4()),
        "session_id": session_id,
        "plan_id": session["plan_id"],
        "athlete_id": session["athlete_id"],
        "block_name": req.block_name.strip(),
        "sets": req.sets,
        "reps": req.reps,
        "rest_seconds": req.rest_seconds,
        "dosage_notes": req.dosage_notes.strip() if req.dosage_notes else None,
        "status": "DRAFT",
        "prescribed_by": req.prescribed_by.strip(),
        "created_at": now,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    TRAINING_DOSAGES[dosage["dosage_id"]] = dosage
    persistence.upsert_training_dosage(dosage)
    log_action(
        req.prescribed_by,
        "TRAINING_DOSAGE_PRESCRIBED",
        session,
        dosage,
        "Dosage prescription recorded for an existing coach-owned session; execution remains separately controlled.",
    )
    return dosage


@app.get("/api/v1/training-sessions/{session_id}/dosage")
def list_training_dosages(session_id: str) -> Dict[str, Any]:
    session = (
        persistence.get_training_session(session_id)
        if persistence.is_postgres_enabled()
        else TRAINING_SESSIONS.get(session_id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="training session not found")
    dosages = (
        persistence.list_training_dosages(session_id)
        if persistence.is_postgres_enabled()
        else [item for item in TRAINING_DOSAGES.values() if item["session_id"] == session_id]
    )
    return {
        "session_id": session_id,
        "total": len(dosages),
        "dosages": dosages,
        "coach_final_authority": True,
        "execution_authorized": False,
    }


@app.get("/api/v1/training-dosages/{dosage_id}")
def get_training_dosage(dosage_id: str) -> Dict[str, Any]:
    dosage = (
        persistence.get_training_dosage(dosage_id)
        if persistence.is_postgres_enabled()
        else TRAINING_DOSAGES.get(dosage_id)
    )
    if dosage is None:
        raise HTTPException(status_code=404, detail="training dosage not found")
    return dosage
'''
if "TRAINING_DOSAGES" not in text:
    if marker not in text:
        raise SystemExit("FEAT-028 main insertion marker not found")
    text = text.replace(marker, feature + marker, 1)
    main.write_text(text)

persistence = root / "backend" / "persistence.py"
p = persistence.read_text()
pfeature = r'''

def _ensure_training_dosages_table() -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_training_dosages (
                    dosage_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    athlete_id TEXT NOT NULL,
                    block_name TEXT NOT NULL,
                    sets INTEGER NOT NULL,
                    reps INTEGER NOT NULL,
                    rest_seconds INTEGER NOT NULL DEFAULT 0,
                    dosage_notes TEXT,
                    status TEXT NOT NULL,
                    prescribed_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        conn.commit()


def upsert_training_dosage(dosage: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    _ensure_training_dosages_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kaizo_training_dosages
                    (dosage_id, session_id, plan_id, athlete_id, block_name, sets, reps,
                     rest_seconds, dosage_notes, status, prescribed_by, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (dosage_id) DO UPDATE SET
                    block_name=EXCLUDED.block_name, sets=EXCLUDED.sets, reps=EXCLUDED.reps,
                    rest_seconds=EXCLUDED.rest_seconds, dosage_notes=EXCLUDED.dosage_notes,
                    status=EXCLUDED.status, prescribed_by=EXCLUDED.prescribed_by
            """, (
                dosage["dosage_id"], dosage["session_id"], dosage["plan_id"], dosage["athlete_id"],
                dosage["block_name"], dosage["sets"], dosage["reps"], dosage["rest_seconds"],
                dosage.get("dosage_notes"), dosage["status"], dosage["prescribed_by"], dosage["created_at"]
            ))
        conn.commit()


def get_training_dosage(dosage_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    _ensure_training_dosages_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT dosage_id, session_id, plan_id, athlete_id, block_name, sets, reps,
                       rest_seconds, dosage_notes, status, prescribed_by, created_at
                FROM kaizo_training_dosages WHERE dosage_id=%s
            """, (dosage_id,))
            r = cur.fetchone()
    if r is None:
        return None
    return {
        "dosage_id": r[0], "session_id": r[1], "plan_id": r[2], "athlete_id": r[3],
        "block_name": r[4], "sets": r[5], "reps": r[6], "rest_seconds": r[7],
        "dosage_notes": r[8], "status": r[9], "prescribed_by": r[10], "created_at": r[11],
        "coach_final_authority": True, "execution_authorized": False,
    }


def list_training_dosages(session_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    _ensure_training_dosages_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT dosage_id, session_id, plan_id, athlete_id, block_name, sets, reps,
                       rest_seconds, dosage_notes, status, prescribed_by, created_at
                FROM kaizo_training_dosages
                WHERE session_id=%s ORDER BY created_at, dosage_id
            """, (session_id,))
            rows = cur.fetchall()
    return [{
        "dosage_id": r[0], "session_id": r[1], "plan_id": r[2], "athlete_id": r[3],
        "block_name": r[4], "sets": r[5], "reps": r[6], "rest_seconds": r[7],
        "dosage_notes": r[8], "status": r[9], "prescribed_by": r[10], "created_at": r[11],
        "coach_final_authority": True, "execution_authorized": False,
    } for r in rows]
'''
if "def upsert_training_dosage" not in p:
    persistence.write_text(p.rstrip() + pfeature + "\n")

test = root / "backend" / "test_feat_028_dosage_reps_sets.py"
test.write_text(r'''from fastapi.testclient import TestClient
import os
import uuid

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"

from backend.main import app


def test_feat_028_dosage_reps_sets():
    client = TestClient(app)
    plan_id = "PLAN-028-" + uuid.uuid4().hex[:8]
    athlete_id = "ATH-028-" + uuid.uuid4().hex[:8]
    decision_id = "DEC-028-" + uuid.uuid4().hex[:8]

    from backend import main
    main.persistence.upsert_training_plan({
        "plan_id": plan_id,
        "athlete_id": athlete_id,
        "decision_id": decision_id,
        "title": "Plan 028",
        "objective": "Dosage prescription",
        "constraints": {},
        "status": "DRAFT",
        "created_by": "coach-028",
        "created_at": "2026-10-06T00:00:00",
    })

    session = client.post(
        f"/api/v1/training-plans/{plan_id}/sessions",
        json={
            "plan_id": plan_id,
            "athlete_id": athlete_id,
            "title": "Session 028",
            "duration_minutes": 60,
            "blocks": [
                {"name": "Technical", "duration_minutes": 40},
                {"name": "Randori", "duration_minutes": 20},
            ],
            "created_by": "coach-028",
        },
    )
    assert session.status_code == 201
    session_id = session.json()["session_id"]

    dosage = client.post(
        f"/api/v1/training-sessions/{session_id}/dosage",
        json={
            "session_id": session_id,
            "block_name": "Technical",
            "sets": 4,
            "reps": 8,
            "rest_seconds": 45,
            "dosage_notes": "Quality entries before speed.",
            "prescribed_by": "coach-028",
        },
    )
    assert dosage.status_code == 201
    body = dosage.json()
    assert body["sets"] == 4
    assert body["reps"] == 8
    assert body["rest_seconds"] == 45
    assert body["status"] == "DRAFT"
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False

    fetched = client.get(f"/api/v1/training-dosages/{body['dosage_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["block_name"] == "Technical"

    listed = client.get(f"/api/v1/training-sessions/{session_id}/dosage")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    invalid = client.post(
        f"/api/v1/training-sessions/{session_id}/dosage",
        json={
            "session_id": session_id,
            "block_name": "Unknown",
            "sets": 3,
            "reps": 5,
            "prescribed_by": "coach-028",
        },
    )
    assert invalid.status_code == 400
''')

workflow = root / ".github" / "workflows" / "apply-feat-028.yml"
workflow.write_text(r'''name: Apply FEAT-028 changes

on:
  push:
    branches:
      - feat-028-dosage-reps-sets

permissions:
  contents: write

jobs:
  apply:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Apply FEAT-028 acceptance step to validation workflow
        run: |
          python - <<'PY'
          from pathlib import Path
          p = Path(".github/workflows/persistence-adapter-validation.yml")
          s = p.read_text()
          marker = "      - name: Run FEAT-027 session structure and timing acceptance tests"
          step = "      - name: Run FEAT-028 dosage reps sets acceptance tests\n        run: PYTHONPATH=.. pytest -q test_feat_028_dosage_reps_sets.py\n"
          if "Run FEAT-028 dosage reps sets acceptance tests" not in s:
              s = s.replace(marker, step + marker, 1)
              p.write_text(s)
          PY
      - name: Commit applied feature
        run: |
          rm -f .github/workflows/apply-feat-028.yml scripts/apply_feat028.py
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add backend/main.py backend/persistence.py backend/test_feat_028_dosage_reps_sets.py .github/workflows/persistence-adapter-validation.yml
          git diff --cached --quiet && exit 0
          git commit -m "feat(FEAT-028): dosage reps sets prescription [skip ci]"
          git push
''')

print("prepared")
