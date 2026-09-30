#!/usr/bin/env bash
set -euo pipefail
BASE="https://kaizo-core-engine-production.up.railway.app"

echo "=== HEALTH ==="
curl -sS -o /tmp/health -w "HTTP=%{http_code}\n" "$BASE/api/v1/health"
cat /tmp/health; echo

echo "=== MISSING_REQUIRED_INPUT ==="
curl -sS -o /tmp/missing -w "HTTP=%{http_code}\n" -X POST "$BASE/api/v1/rules/evaluate" -H "Content-Type: application/json" -d '{"athlete_id":"GAP-02-MISSING-001","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength"}'
cat /tmp/missing; echo

echo "=== CONFLICT_UNSUPPORTED_PROFILE ==="
curl -sS -o /tmp/conflict -w "HTTP=%{http_code}\n" -X POST "$BASE/api/v1/rules/evaluate" -H "Content-Type: application/json" -d '{"athlete_id":"GAP-02-CONFLICT-001","age_group":"under15","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":18.0}'
cat /tmp/conflict; echo

echo "=== VALID_CONTROL ==="
curl -sS -o /tmp/control -w "HTTP=%{http_code}\n" -X POST "$BASE/api/v1/rules/evaluate" -H "Content-Type: application/json" -d '{"athlete_id":"GAP-02-CONTROL-001","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":18.0}'
cat /tmp/control; echo
