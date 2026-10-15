#!/usr/bin/env bash
set -euo pipefail
BASE_URL="https://kaizo-core-engine-production.up.railway.app"
HEALTH=$(curl -fsS "$BASE_URL/api/v1/health")
python -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="Online"' <<<"$HEALTH"

VALID=$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H "Content-Type: application/json" --data '{"athlete_id":"PACK-C-REDTEAM","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":20}')
echo "$VALID"
python -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="HOLD"; assert d["reason_code"]=="NUMERIC_CLAIM_VALIDATION_REQUIRED"; assert d["decision_blocked"] is True' <<<"$VALID"

MISSING=$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H "Content-Type: application/json" --data '{"athlete_id":"PACK-C-MISSING","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":null}')
echo "$MISSING"
python -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="HOLD"; assert d["reason_code"]=="MISSING_REQUIRED_INPUT"' <<<"$MISSING"

# Public audit-log listing must remain fail-closed until verified identity and
# tenant-scoped authorization are deployed. Do not treat a 503 as a test failure.
AUDIT_RESPONSE=$(curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/v1/audit/logs")
echo "$AUDIT_RESPONSE"
grep -q 'HTTP_STATUS:503' <<<"$AUDIT_RESPONSE"
grep -q 'disabled pending verified identity and tenant authorization' <<<"$AUDIT_RESPONSE"
echo "PACK-C PRODUCTION NUMERIC-GOVERNANCE RED TEAM: PASS"
