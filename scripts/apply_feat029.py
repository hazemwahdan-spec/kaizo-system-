from pathlib import Path
root=Path(__file__).resolve().parents[1]

main=root/"backend/main.py"
s=main.read_text()
if "ProgressionRegressionRuleRequest" not in s:
    s += r'''

class ProgressionRegressionRuleRequest(BaseModel):
    plan_id: str
    rule_name: str
    trigger_metric: str
    operator: str
    threshold: float
    action: str
    adjustment: float
    created_by: str


@app.post("/api/v1/training-plans/{plan_id}/progression-rules", status_code=status.HTTP_201_CREATED)
def create_progression_rule(plan_id: str, req: ProgressionRegressionRuleRequest) -> Dict[str, Any]:
    if req.plan_id != plan_id:
        raise HTTPException(status_code=400, detail="plan_id mismatch")
    if not req.rule_name.strip() or not req.trigger_metric.strip() or not req.action.strip() or not req.created_by.strip():
        raise HTTPException(status_code=400, detail="rule_name, trigger_metric, action and created_by are required")
    if req.operator not in {"GT", "GTE", "LT", "LTE", "EQ"}:
        raise HTTPException(status_code=400, detail="invalid operator")
    if req.action not in {"PROGRESS", "REGRESS", "HOLD"}:
        raise HTTPException(status_code=400, detail="invalid action")
    if req.adjustment <= 0:
        raise HTTPException(status_code=400, detail="adjustment must be positive")

    plan = persistence.get_training_plan(plan_id) if persistence.is_postgres_enabled() else TRAINING_PLANS.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="training plan not found")

    import uuid
    rule = {
        "rule_id": str(uuid.uuid4()),
        "plan_id": plan_id,
        "rule_name": req.rule_name.strip(),
        "trigger_metric": req.trigger_metric.strip(),
        "operator": req.operator,
        "threshold": req.threshold,
        "action": req.action,
        "adjustment": req.adjustment,
        "status": "DRAFT",
        "created_by": req.created_by.strip(),
        "created_at": datetime.utcnow().isoformat(),
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    persistence.upsert_progression_rule(rule)
    log_action(req.created_by, "PROGRESSION_REGRESSION_RULE_CREATED", plan, rule,
               "Progression/regression rule recorded for coach review; execution remains disabled.")
    return rule


@app.get("/api/v1/training-plans/{plan_id}/progression-rules")
def list_progression_rules(plan_id: str) -> Dict[str, Any]:
    plan = persistence.get_training_plan(plan_id) if persistence.is_postgres_enabled() else TRAINING_PLANS.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="training plan not found")
    return {
        "plan_id": plan_id,
        "rules": persistence.list_progression_rules(plan_id),
        "coach_final_authority": True,
        "execution_authorized": False,
    }


@app.get("/api/v1/progression-rules/{rule_id}")
def get_progression_rule(rule_id: str) -> Dict[str, Any]:
    rule = persistence.get_progression_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="progression/regression rule not found")
    return rule
'''
    main.write_text(s)

p=root/"backend/persistence.py"
s=p.read_text()
if "def upsert_progression_rule" not in s:
    s += r'''

def _ensure_progression_rules_table() -> None:
    if not is_postgres_enabled():
        return
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_progression_rules (
                    rule_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    trigger_metric TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    threshold DOUBLE PRECISION NOT NULL,
                    action TEXT NOT NULL,
                    adjustment DOUBLE PRECISION NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        conn.commit()


def upsert_progression_rule(rule: Dict[str, Any]) -> None:
    if not is_postgres_enabled():
        return
    _ensure_progression_rules_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kaizo_progression_rules
                (rule_id,plan_id,rule_name,trigger_metric,operator,threshold,action,adjustment,status,created_by,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (rule_id) DO UPDATE SET
                rule_name=EXCLUDED.rule_name, trigger_metric=EXCLUDED.trigger_metric,
                operator=EXCLUDED.operator, threshold=EXCLUDED.threshold,
                action=EXCLUDED.action, adjustment=EXCLUDED.adjustment,
                status=EXCLUDED.status, created_by=EXCLUDED.created_by
            """, (rule["rule_id"],rule["plan_id"],rule["rule_name"],rule["trigger_metric"],
                  rule["operator"],rule["threshold"],rule["action"],rule["adjustment"],
                  rule["status"],rule["created_by"],rule["created_at"]))
        conn.commit()


def _progression_rule(row) -> Dict[str, Any]:
    return {"rule_id":row[0],"plan_id":row[1],"rule_name":row[2],"trigger_metric":row[3],
            "operator":row[4],"threshold":row[5],"action":row[6],"adjustment":row[7],
            "status":row[8],"created_by":row[9],"created_at":row[10],
            "coach_final_authority":True,"execution_authorized":False}


def get_progression_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    if not is_postgres_enabled():
        return None
    _ensure_progression_rules_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT rule_id,plan_id,rule_name,trigger_metric,operator,threshold,action,adjustment,status,created_by,created_at FROM kaizo_progression_rules WHERE rule_id=%s",(rule_id,))
            row=cur.fetchone()
    return None if row is None else _progression_rule(row)


def list_progression_rules(plan_id: str) -> list[Dict[str, Any]]:
    if not is_postgres_enabled():
        return []
    _ensure_progression_rules_table()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT rule_id,plan_id,rule_name,trigger_metric,operator,threshold,action,adjustment,status,created_by,created_at FROM kaizo_progression_rules WHERE plan_id=%s ORDER BY created_at,rule_id",(plan_id,))
            rows=cur.fetchall()
    return [_progression_rule(row) for row in rows]
'''
    p.write_text(s)

t=root/"backend/test_feat_029_progression_regression.py"
t.write_text(r'''from fastapi.testclient import TestClient
import os, uuid
os.environ["KAIZO_PERSISTENCE_MODE"]="postgres"
from backend.main import app

def test_feat_029_progression_regression():
    client=TestClient(app)
    plan_id="PLAN-029-"+uuid.uuid4().hex[:8]
    athlete_id="ATH-029-"+uuid.uuid4().hex[:8]
    decision_id="DEC-029-"+uuid.uuid4().hex[:8]
    from backend import main
    main.persistence.upsert_training_plan({
        "plan_id":plan_id,"athlete_id":athlete_id,"decision_id":decision_id,
        "title":"Plan 029","objective":"Progression rules","constraints":{},
        "status":"DRAFT","created_by":"coach-029","created_at":"2026-10-06T00:00:00"
    })
    r=client.post(f"/api/v1/training-plans/{plan_id}/progression-rules",json={
        "plan_id":plan_id,"rule_name":"Increase volume after quality target",
        "trigger_metric":"technical_quality","operator":"GTE","threshold":8,
        "action":"PROGRESS","adjustment":2,"created_by":"coach-029"})
    assert r.status_code==201
    body=r.json()
    assert body["action"]=="PROGRESS"
    assert body["adjustment"]==2
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False
    g=client.get(f"/api/v1/progression-rules/{body['rule_id']}")
    assert g.status_code==200
    assert g.json()["rule_name"]=="Increase volume after quality target"
    l=client.get(f"/api/v1/training-plans/{plan_id}/progression-rules")
    assert l.status_code==200
    assert len(l.json()["rules"])==1
    bad=client.post(f"/api/v1/training-plans/{plan_id}/progression-rules",json={
        "plan_id":plan_id,"rule_name":"Bad","trigger_metric":"x","operator":"BAD",
        "threshold":1,"action":"PROGRESS","adjustment":1,"created_by":"coach-029"})
    assert bad.status_code==400
''')

w=root/".github/workflows/feat-029-validation.yml"
w.write_text(r'''name: FEAT-029 Acceptance
on:
  pull_request:
    branches: [main]
    paths:
      - "backend/main.py"
      - "backend/persistence.py"
      - "backend/test_feat_029_progression_regression.py"
      - ".github/workflows/feat-029-validation.yml"
permissions:
  contents: read
jobs:
  acceptance:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: kaizo_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres -d kaizo_test"
          --health-interval 5s --health-timeout 5s --health-retries 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - name: Install
        working-directory: backend
        run: pip install -r requirements.txt
      - name: Test
        working-directory: backend
        env:
          KAIZO_PERSISTENCE_MODE: postgres
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/kaizo_test
        run: pip install pytest && PYTHONPATH=.. pytest -q test_feat_029_progression_regression.py
''')
print("done")
