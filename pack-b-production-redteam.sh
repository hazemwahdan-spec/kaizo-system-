#!/usr/bin/env bash
set -euo pipefail
BASE_URL="https://kaizo-core-engine-production.up.railway.app"
RUN_ID="${GITHUB_RUN_ID:-manual}"
ENTITY="pack-b-$RUN_ID"
CASE="PACK-B-$RUN_ID"

for i in $(seq 1 30); do
  code=$(curl -sS -o /tmp/health.json -w "%{http_code}" "$BASE_URL/api/v1/health" || true)
  if [ "$code" = "200" ] && python -c 'import json; assert json.load(open("/tmp/health.json")).get("status")=="Online"'; then
    cat /tmp/health.json
    break
  fi
  sleep 10
done
[ "${code:-}" = "200" ]

payload=$(jq -n --arg case "$CASE" --arg entity "$ENTITY" '{case_id:$case,entity_id:$entity,state:{kpi:1,phase:"post-intervention"},source_event:"production_retest"}')
valid=$(curl -fsS -X POST "$BASE_URL/api/v1/digital-twin/sync" -H "Content-Type: application/json" --data "$payload")
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["status"]=="SYNCHRONIZED"; assert d["sync"]["new_version"]==1' "$valid"

twin=$(curl -fsS "$BASE_URL/api/v1/digital-twin/$ENTITY")
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["status"]=="SYNCHRONIZED"; assert d["digital_twin_state"]["version"]==1' "$twin"

payload=$(jq -n --arg case "${CASE}-CONFLICT" --arg entity "$ENTITY" '{case_id:$case,entity_id:$entity,state:{kpi:2},source_event:"stale_retest",expected_version:0}')
conflict=$(curl -fsS -X POST "$BASE_URL/api/v1/digital-twin/sync" -H "Content-Type: application/json" --data "$payload")
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["status"]=="HOLD"; assert d["reason_code"]=="DIGITAL_TWIN_VERSION_CONFLICT"; assert d["resolution_required"] is True' "$conflict"

payload=$(jq -n --arg case "${CASE}-MISSING" --arg entity "$ENTITY" '{case_id:$case,entity_id:$entity,state:{},source_event:""}')
missing=$(curl -fsS -X POST "$BASE_URL/api/v1/digital-twin/sync" -H "Content-Type: application/json" --data "$payload")
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["status"]=="HOLD"; assert d["reason_code"]=="MISSING_DIGITAL_TWIN_INPUT"; assert d["diagnostic_required"] is True' "$missing"

payload=$(jq -n --arg case "${CASE}-AUTH" --arg entity "$ENTITY" '{case_id:$case,entity_id:$entity,state:{kpi:3},source_event:"unauthorized",coach_final_authority:false}')
authority=$(curl -fsS -X POST "$BASE_URL/api/v1/digital-twin/sync" -H "Content-Type: application/json" --data "$payload")
python -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["status"]=="HOLD"; assert d["reason_code"]=="COACH_FINAL_AUTHORITY_REQUIRED"; assert d["diagnostic_required"] is True' "$authority"

audit=$(curl -fsS "$BASE_URL/api/v1/audit/logs")
python -c 'import json,sys; d=json.loads(sys.argv[1]); events=[x.get("action") for x in d.get("logs",[])]; assert "DIGITAL_TWIN_SYNCHRONIZED" in events; assert "DIGITAL_TWIN_SYNC_HOLD" in events' "$audit"
echo "PACK-B PRODUCTION RED TEAM: PASS"
