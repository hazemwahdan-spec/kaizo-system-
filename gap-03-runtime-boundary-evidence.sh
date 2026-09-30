#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:?BASE_URL is required}"
PASS=0
FAIL=0
check(){ local n="$1" b="$2" x="$3"; if printf '%s' "$b"|grep -Fq "$x";then echo "PASS|$n|$x";PASS=$((PASS+1));else echo "FAIL|$n|missing:$x";FAIL=$((FAIL+1));fi; }
h="$(curl -fsS "$BASE_URL/api/v1/health")"; check "health" "$h" '"status":"Online"'
v="$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H 'Content-Type: application/json' -d '{"athlete_id":"GAP03-BASE","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":18}')"
check "decision" "$v" '"status":"DECISION"'; check "decision" "$v" '"evaluation":"Average"'
m="$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H 'Content-Type: application/json' -d '{"athlete_id":"GAP03-MISSING","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength"}')"
check "missing-hold" "$m" '"status":"HOLD"'; check "missing-hold" "$m" '"diagnostic_required":true'
c="$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H 'Content-Type: application/json' -d '{"athlete_id":"GAP03-CONFLICT","age_group":"under13","gender":"male","weight_category":"-46kg","metric_name":"grip_strength","actual_value":18}')"
check "conflict-hold" "$c" '"status":"HOLD"'; check "conflict-hold" "$c" '"reason_code":"SOURCE_CONFLICT_VALIDATION_REQUIRED"'
a="$(curl -fsS "$BASE_URL/api/v1/audit/logs")"; check "audit" "$a" '"system":"KAIZO Audit-Ready System"'
echo "UNIMPLEMENTED|G03-R01=CommonCore->IndividualAdaptation|G03-R02=CommonCore->TeamAdaptation|G03-R03=CompositionChange->SubgroupRecalculation|G03-R04=IndividualChange->IsolatedOutputChange|G03-R05=Conflict->HOLD"
echo "SUMMARY|PASS=$PASS|FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
