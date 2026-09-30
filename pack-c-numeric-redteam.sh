#!/usr/bin/env bash
set -euo pipefail
BASE_URL="https://kaizo-core-engine-production.up.railway.app"
HEALTH=$(curl -fsS "$BASE_URL/api/v1/health")
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["status"]=="Online"' "$HEALTH"

VALID=$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H "Content-Type: application/json" --data '{"athlete_id":"PACK-C-REDTEAM","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":20}')
echo "$VALID"
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["status"]=="HOLD"; assert d["reason_code"]=="NUMERIC_CLAIM_VALIDATION_REQUIRED"; assert d["decision_blocked"] is True' "$VALID"

MISSING=$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H "Content-Type: application/json" --data '{"athlete_id":"PACK-C-MISSING","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":null}')
echo "$MISSING"
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["status"]=="HOLD"; assert d["reason_code"]=="MISSING_REQUIRED_INPUT"' "$MISSING"

AUDIT=$(curl -fsS "$BASE_URL/api/v1/audit/logs")
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert any(x.get("action")=="NUMERIC_CLAIM_VALIDATION_HOLD" for x in d.get("logs",[]))' "$AUDIT"
echo "PACK-C PRODUCTION NUMERIC-GOVERNANCE RED TEAM: PASS"
