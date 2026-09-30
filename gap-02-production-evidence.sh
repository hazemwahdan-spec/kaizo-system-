#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:?BASE_URL is required}"
PASS=0
FAIL=0

assert_contains() {
  local name="$1" body="$2" needle="$3"
  if printf '%s' "$body" | grep -Fq "$needle"; then
    echo "PASS|$name|$needle"
    PASS=$((PASS+1))
  else
    echo "FAIL|$name|missing:$needle|body:$body"
    FAIL=$((FAIL+1))
  fi
}

health="$(curl -fsS "$BASE_URL/api/v1/health")"
assert_contains "health" "$health" '"status":"Online"'

missing="$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H 'Content-Type: application/json' -d '{"athlete_id":"GAP02-MISSING","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength"}')"
assert_contains "missing_required_input" "$missing" '"status":"HOLD"'
assert_contains "missing_required_input" "$missing" '"reason_code":"MISSING_REQUIRED_INPUT"'
assert_contains "missing_required_input" "$missing" '"diagnostic_required":true'

conflict="$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H 'Content-Type: application/json' -d '{"athlete_id":"GAP02-CONFLICT","age_group":"under13","gender":"male","weight_category":"-46kg","metric_name":"grip_strength","actual_value":18}')"
assert_contains "unsupported_profile" "$conflict" '"status":"HOLD"'
assert_contains "unsupported_profile" "$conflict" '"reason_code":"SOURCE_CONFLICT_VALIDATION_REQUIRED"'
assert_contains "unsupported_profile" "$conflict" '"diagnostic_required":true'

valid="$(curl -fsS -X POST "$BASE_URL/api/v1/rules/evaluate" -H 'Content-Type: application/json' -d '{"athlete_id":"GAP02-VALID","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":18}')"
assert_contains "valid_control" "$valid" '"status":"DECISION"'
assert_contains "valid_control" "$valid" '"evaluation":"Average"'
assert_contains "valid_control" "$valid" '"recommendation":"Grip Endurance Protocol A (SOL-000032)"'

invalid_status="$(curl -sS -o /tmp/gap02-invalid.json -w '%{http_code}' -X POST "$BASE_URL/api/v1/rules/evaluate" -H 'Content-Type: application/json' -d '{"athlete_id":"GAP02-REDTEAM","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":"not-a-number"}')"
if [ "$invalid_status" = "422" ]; then
  echo "PASS|red_team_invalid_type|HTTP 422"
  PASS=$((PASS+1))
else
  echo "FAIL|red_team_invalid_type|HTTP $invalid_status"
  FAIL=$((FAIL+1))
fi

audit="$(curl -fsS "$BASE_URL/api/v1/audit/logs")"
assert_contains "audit_endpoint" "$audit" '"system":"KAIZO Audit-Ready System"'
assert_contains "audit_endpoint" "$audit" '"total_logs"'

echo "SUMMARY|PASS=$PASS|FAIL=$FAIL"
if [ "$FAIL" -ne 0 ]; then exit 1; fi
