#!/usr/bin/env bash
set -euo pipefail
BASE="https://kaizo-core-engine-production.up.railway.app"
# Missing required input: omit actual_value. FastAPI/Pydantic must reject the request.
code=$(curl -sS -o /tmp/missing -w "%{http_code}" -X POST "$BASE/api/v1/rules/evaluate" -H "Content-Type: application/json" -d '{"athlete_id":"GAP-02-MISSING-001","age_group":"under11","gender":"male","weight_category":"-42kg","metric_name":"grip_strength"}')
echo "MISSING_INPUT_HTTP=$code"
cat /tmp/missing
echo
# Unsupported parameter combination: runtime must block rather than produce a decision.
code=$(curl -sS -o /tmp/conflict -w "%{http_code}" -X POST "$BASE/api/v1/rules/evaluate" -H "Content-Type: application/json" -d '{"athlete_id":"GAP-02-CONFLICT-001","age_group":"under15","gender":"male","weight_category":"-42kg","metric_name":"grip_strength","actual_value":18.0}')
echo "UNSUPPORTED_INPUT_HTTP=$code"
cat /tmp/conflict
echo
# HOLD is not asserted here: this probe is intentionally evidence-only and does not mutate production.
