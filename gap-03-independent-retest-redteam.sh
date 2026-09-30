#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-https://kaizo-core-engine-production.up.railway.app}"
post(){ curl -sS -w "\nHTTP_STATUS:%{http_code}\n" -X POST "$BASE_URL/api/v1/decision/adapt" -H 'Content-Type: application/json' -d "$1"; }
expect_hold(){ out="$("$@" 2>/dev/null || true)"; echo "$out"; grep -q '"status":"HOLD"' <<<"$out"; }
expect_422(){ out="$(curl -sS -w "\nHTTP_STATUS:%{http_code}\n" -X POST "$BASE_URL/api/v1/decision/adapt" -H 'Content-Type: application/json' -d "$1")"; echo "$out"; grep -q 'HTTP_STATUS:422' <<<"$out"; }

echo "G03-IR01"; post '{"case_id":"G03-IR01","operation":"individual_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"player_state":"retested"},"individual_change":{"task":"independent-retest"}}'
echo "G03-IR02"; post '{"case_id":"G03-IR02","operation":"team_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"team_state":"retested"},"team_change":{"subgroup":"independent-retest"}}'
echo "G03-IR03"; post '{"case_id":"G03-IR03","operation":"subgroup_recalculation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"composition":"retested"},"composition_change":{"added":"athlete-X","removed":"athlete-Y"}}'
echo "G03-IR04"; post '{"case_id":"G03-IR04","operation":"individual_change","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"player_state":"retested"},"individual_change":{"task":"independent-change"}}'

echo "REDTEAM-MISSING-CORE"; expect_422 '{"case_id":"G03-RT-MISSING-CORE","operation":"individual_adaptation","dynamic_inputs":{"player_state":"ok"}}'
echo "REDTEAM-MISSING-DYNAMIC"; expect_422 '{"case_id":"G03-RT-MISSING-DYNAMIC","operation":"team_adaptation","common_core":{"plan":"CORE-A"}}'
echo "REDTEAM-UNSUPPORTED"; expect_hold bash -c 'curl -sS -X POST "$0/api/v1/decision/adapt" -H "Content-Type: application/json" -d "$1"' "$BASE_URL" '{"case_id":"G03-RT-UNSUPPORTED","operation":"unknown_operation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"state":"ok"}}'
echo "REDTEAM-AUTHORITY"; expect_hold bash -c 'curl -sS -X POST "$0/api/v1/decision/adapt" -H "Content-Type: application/json" -d "$1"' "$BASE_URL" '{"case_id":"G03-RT-AUTHORITY","operation":"individual_adaptation","common_core":{"plan":"CORE-A"},"dynamic_inputs":{"state":"ok"},"coach_final_authority":false}'

echo "AUDIT"; curl -fsS "$BASE_URL/api/v1/audit/logs"; echo
