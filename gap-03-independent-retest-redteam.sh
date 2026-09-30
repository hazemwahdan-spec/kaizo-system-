#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-https://kaizo-core-engine-production.up.railway.app}"
post(){ curl -fsS -X POST "$BASE_URL/api/v1/decision/adapt" -H 'Content-Type: application/json' -d "$1"; echo; }
get(){ curl -fsS "$BASE_URL$1"; echo; }

echo "G03-IR01"; post '{"case_id":"G03-IR01","operation":"individual_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"player_state":"retested"},"individual_change":{"task":"independent-retest"}}'
echo "G03-IR02"; post '{"case_id":"G03-IR02","operation":"team_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"team_state":"retested"},"team_change":{"subgroup":"independent-retest"}}'
echo "G03-IR03"; post '{"case_id":"G03-IR03","operation":"subgroup_recalculation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"composition":"retested"},"composition_change":{"added":"athlete-X","removed":"athlete-Y"}}'
echo "G03-IR04"; post '{"case_id":"G03-IR04","operation":"individual_change","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"player_state":"retested"},"individual_change":{"task":"independent-change"}}'

echo "REDTEAM-MISSING-CORE"; post '{"case_id":"G03-RT-MISSING-CORE","operation":"individual_adaptation","dynamic_inputs":{"player_state":"ok"}}'
echo "REDTEAM-MISSING-DYNAMIC"; post '{"case_id":"G03-RT-MISSING-DYNAMIC","operation":"team_adaptation","common_core":{"plan":"CORE-A"}}'
echo "REDTEAM-UNSUPPORTED"; post '{"case_id":"G03-RT-UNSUPPORTED","operation":"unknown_operation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"state":"ok"}}'
echo "REDTEAM-AUTHORITY"; post '{"case_id":"G03-RT-AUTHORITY","operation":"individual_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"state":"ok"},"coach_final_authority":false}'

echo "AUDIT"; get "/api/v1/audit/logs"
